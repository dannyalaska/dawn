# app/api/rag.py
from __future__ import annotations

import contextlib
import hashlib
import json
from io import BytesIO
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi import Query as FQuery
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import ResponseError
from sqlalchemy import select

from app.core.db import session_scope
from app.core.excel.summary import summarize_dataframe
from app.core.llm import answer as llm_answer
from app.core.models import Upload
from app.core.rag import (
    Chunk,
    add_manual_note,
    format_context,
    list_context_chunks,
    search,
    simple_chunker,
    update_context_chunk,
    upsert_chunks,
)
from app.core.redis_client import redis_sync

router = APIRouter(prefix="/rag", tags=["rag"])

# Avoid Ruff B008: evaluate File(...) at import time, then use in signature
file_param = File(...)


@router.post("/index_excel")
async def index_excel(
    file: UploadFile = file_param,
    sheet: str | None = FQuery(default=None),
    chunk_max_chars: int = FQuery(default=600, ge=128, le=2000),
    chunk_overlap: int = FQuery(default=80, ge=0, le=600),
) -> dict:
    name = file.filename or "upload.xlsx"
    data = await file.read()
    try:
        xl = pd.ExcelFile(BytesIO(data))
    except Exception as e:
        raise HTTPException(400, f"Failed to read Excel: {e}") from e

    normalized_sheet = sheet.strip() if isinstance(sheet, str) else None
    if not normalized_sheet:
        if not xl.sheet_names:
            raise HTTPException(400, "Excel file appears to have no sheets.")
        actual_sheet = xl.sheet_names[0]
    else:
        if normalized_sheet not in xl.sheet_names:
            raise HTTPException(
                400,
                f"Sheet '{normalized_sheet}' not found. Available sheets: {', '.join(xl.sheet_names)}",
            )
        actual_sheet = normalized_sheet

    if chunk_overlap >= chunk_max_chars:
        raise HTTPException(400, "chunk_overlap must be less than chunk_max_chars")

    try:
        df = xl.parse(actual_sheet)
    except Exception as e:
        raise HTTPException(400, f"Failed to read sheet '{actual_sheet}': {e}") from e

    digest = hashlib.sha256(data).hexdigest()[:16]
    df_original = df.copy()
    summary_text, column_summaries, dataset_metrics, summary_extras = summarize_dataframe(
        df_original
    )
    df_text = df_original.fillna("").astype(str)
    summary_lines = [summary_text]
    for metric in dataset_metrics:
        values_preview = ", ".join(f"{label}: {count}" for label, count in metric.values[:3])
        if values_preview:
            summary_lines.append(f"{metric.description or metric.column}: {values_preview}")
    combined_summary = "\n".join(summary_lines)
    chunks: list[Chunk] = []
    src = f"{name}:{actual_sheet}"
    if combined_summary:
        for piece in simple_chunker(combined_summary, max_chars=900, overlap=0):
            chunks.append(
                Chunk(text=f"Summary for {src}: {piece}", source=f"{src}:summary", row_index=-1)
            )
    for i, row in df_text.iterrows():
        row_text = " | ".join(f"{col}: {row[col]}" for col in df_text.columns)
        for piece in simple_chunker(row_text, max_chars=chunk_max_chars, overlap=chunk_overlap):
            chunks.append(Chunk(text=piece, source=src, row_index=int(i)))

    n = upsert_chunks(chunks)

    summary_payload = {
        "text": combined_summary,
        "columns": [
            {
                "name": cs.name,
                "dtype": cs.dtype,
                "top_values": cs.top_values,
                "stats": cs.stats,
            }
            for cs in column_summaries
        ],
        "metrics": [
            {
                "type": metric.type,
                "column": metric.column,
                "values": [{"label": label, "count": count} for label, count in metric.values],
                "description": metric.description,
            }
            for metric in dataset_metrics
        ],
        "insights": summary_extras.get("counts", {}),
        "aggregates": summary_extras.get("aggregates", []),
        "relationships": summary_extras.get("relationships", {}),
        "analysis_plan": summary_extras.get("plan", []),
    }

    size_bytes = len(data)
    row_count = int(len(df_original))
    col_count = int(len(df_original.columns))

    with session_scope() as s:
        stmt = (
            select(Upload)
            .where(Upload.sha16 == digest, Upload.sheet == actual_sheet)
            .order_by(Upload.uploaded_at.desc())
            .limit(1)
        )
        existing = s.execute(stmt).scalars().first()
        if existing:
            existing.summary = summary_payload
            existing.rows = row_count
            existing.cols = col_count
            existing.size_bytes = size_bytes
        else:
            s.add(
                Upload(
                    filename=name,
                    sheet=actual_sheet,
                    sha16=digest,
                    size_bytes=size_bytes,
                    rows=row_count,
                    cols=col_count,
                    summary=summary_payload,
                )
            )

    return {
        "indexed_chunks": n,
        "rows": row_count,
        "source": name,
        "sheet": actual_sheet,
        "sha16": digest,
        "summary": summary_payload,
        "chunk_config": {
            "max_chars": chunk_max_chars,
            "overlap": chunk_overlap,
        },
    }


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    k: int = Field(default=12, ge=1, le=50)


class ContextUpdateRequest(BaseModel):
    text: str = Field(min_length=1)


class ContextNoteRequest(BaseModel):
    source: str = Field(min_length=3)
    text: str = Field(min_length=1)


class MemoryUpdateRequest(BaseModel):
    sha16: str = Field(min_length=4)
    sheet: str
    relationships: dict[str, str] | None = None
    analysis_plan: list[dict[str, Any]] | None = Field(default=None, alias="plan")

    model_config = ConfigDict(populate_by_name=True)


def _source_to_file_sheet(source: str) -> tuple[str, str] | None:
    base = source
    if base.endswith(":summary"):
        base = base.rsplit(":", 1)[0]
    parts = base.split(":", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _load_summary_for_source(source: str) -> dict[str, Any] | None:
    parsed = _source_to_file_sheet(source)
    if not parsed:
        return None
    filename, sheet = parsed
    with session_scope() as s:
        stmt = (
            select(Upload)
            .where(Upload.filename == filename, Upload.sheet == sheet)
            .order_by(Upload.uploaded_at.desc())
            .limit(1)
        )
        rec = s.execute(stmt).scalars().first()
        if rec and rec.summary:
            return dict(rec.summary)
    return None


_MOST_KEYWORDS = ("most", "highest", "largest", "top", "greatest")
_LEAST_KEYWORDS = ("fewest", "least", "lowest", "smallest")
_FAST_KEYWORDS = ("fastest", "quickest", "shortest", "lowest", "best")
_SLOW_KEYWORDS = ("slowest", "longest", "highest", "worst")


def _match_column(
    question_lower: str, insights: dict[str, Any], relationships: dict[str, str]
) -> str | None:
    for col, role in relationships.items():
        role_lower = (role or "").lower()
        col_lower = col.lower()
        if role_lower and role_lower in question_lower:
            return col
        if col_lower in question_lower:
            return col
    for col in insights:
        if col.lower() in question_lower:
            return col
    # resolver-specific fallback
    if any(word in question_lower for word in ("ticket", "resolve", "assigned", "who")):
        for col, role in relationships.items():
            if (role or "").lower() in {"resolver", "owner", "assignee", "agent"}:
                return col
    return None


def _direct_answer_from_summary(question: str, summary: dict[str, Any]) -> str | None:
    q = question.lower()
    insights = summary.get("insights") or {}
    relationships = {str(k): str(v) for k, v in (summary.get("relationships") or {}).items()}
    aggregates = summary.get("aggregates") or []

    # Count-based questions (most / fewest)
    if insights and any(keyword in q for keyword in _MOST_KEYWORDS + _LEAST_KEYWORDS):
        column = _match_column(q, insights, relationships)
        if column and column in insights:
            entries = insights.get(column) or []
            if entries:
                descending = not any(keyword in q for keyword in _LEAST_KEYWORDS)
                descriptor = "most" if descending else "fewest"
                sorted_entries = sorted(entries, key=lambda e: int(e.get("count", 0)), reverse=True)
                if not descending:
                    sorted_entries = list(reversed(sorted_entries))
                top_entry = sorted_entries[0]
                others = ", ".join(
                    f"{entry['label']} ({entry['count']})" for entry in sorted_entries[1:3]
                )
                headline = (
                    f"{top_entry['label']} handled the {descriptor} tickets ({top_entry['count']})."
                )
                if others:
                    headline += f" Next: {others}."
                return headline

    # Aggregate-based questions (fastest / slowest)
    target: str | None = None
    speed_descriptor: str | None = None
    if any(keyword in q for keyword in _FAST_KEYWORDS):
        target = "best"
        speed_descriptor = "fastest"
    elif any(keyword in q for keyword in _SLOW_KEYWORDS):
        target = "worst"
        speed_descriptor = "slowest"

    if target and aggregates:
        for agg in aggregates:
            group = str(agg.get("group", ""))
            value = str(agg.get("value", ""))
            role = (relationships.get(group) or "").lower()
            if not group:
                continue
            if group.lower() in q or (role and role in q) or (role == "resolver" and "ticket" in q):
                entries = agg.get(target) or []
                if entries:
                    entry = entries[0]
                    metric_value = entry.get("value")
                    if isinstance(metric_value, (int | float)):
                        value_str = f"{metric_value:.2f}"
                    else:
                        value_str = str(metric_value)
                    value_name = str(value or "metric")
                    nice_value = value_name.replace("_", " ")
                    descriptor_label = speed_descriptor or "fastest"
                    answer = f"{entry.get('label')} is the {descriptor_label} for {nice_value} ({value_str})."
                    peers = ", ".join(
                        (
                            f"{e['label']} ({e['value']:.2f})"
                            if isinstance(e.get("value"), (int | float))
                            else f"{e['label']} ({e.get('value')})"
                        )
                        for e in entries[1:3]
                    )
                    if peers:
                        answer += f" Next: {peers}."
                    return answer

    return None


@router.post("/chat")
def rag_chat(payload: ChatRequest) -> dict[str, Any]:
    if payload.messages[-1].role != "user":
        raise HTTPException(400, "Last message must be from the user.")

    question = payload.messages[-1].content
    hits = search(question, k=payload.k)
    ctx = format_context(hits, limit_chars=2500)

    summary_payload: dict[str, Any] | None = None
    direct_answer: str | None = None
    for hit in hits:
        summary_payload = _load_summary_for_source(hit.get("source", ""))
        if summary_payload:
            direct_answer = _direct_answer_from_summary(question, summary_payload)
            if direct_answer:
                break

    history_lines = [f"{msg.role.capitalize()}: {msg.content}" for msg in payload.messages[:-1]]
    if history_lines:
        history_block = "\n".join(history_lines)
        ctx = f"Conversation so far:\n{history_block}\n\nRetrieved data:\n{ctx}"

    if direct_answer:
        answer_text = direct_answer
    else:
        answer_text = (
            llm_answer(question, ctx, hits)
            if hits
            else (
                "I don't have enough context yet. Try indexing more data or restating the question."
            )
        )

    updated_messages = payload.messages + [ChatMessage(role="assistant", content=answer_text)]
    return {
        "answer": answer_text,
        "sources": hits,
        "messages": [m.model_dump() for m in updated_messages],
    }


@router.get("/query")
def rag_query(q: str, k: int = 5) -> dict:
    hits = search(q, k=k)
    ctx = format_context(hits)
    # Placeholder generator; plug in your LLM later.
    answer = (
        "Context-based answer (stub):\n\n"
        f"{ctx}\n\n"
        "— End of retrieved context. Replace this with an LLM call that cites [1], [2], ..."
    )
    return {"query": q, "answer": answer, "sources": hits}


@router.get("/context")
def list_context(
    source: str = FQuery(...), limit: int = FQuery(default=200, ge=1, le=500)
) -> dict[str, Any]:
    source_clean = source.strip()
    if not source_clean:
        raise HTTPException(400, "source must be provided")
    chunks = list_context_chunks(source=source_clean, limit=limit)
    return {"source": source_clean, "count": len(chunks), "chunks": chunks}


@router.put("/context/{chunk_id}")
def update_context(chunk_id: str, payload: ContextUpdateRequest) -> dict[str, Any]:
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "text cannot be empty")
    try:
        updated = update_context_chunk(chunk_id, text)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"updated": updated}


@router.post("/context/note")
def add_context(payload: ContextNoteRequest) -> dict[str, Any]:
    source = payload.source.strip()
    text = payload.text.strip()
    if not source:
        raise HTTPException(400, "source cannot be empty")
    if not text:
        raise HTTPException(400, "text cannot be empty")
    created = add_manual_note(source, text)
    return {"created": created}


@router.get("/memory")
def get_memory(sha16: str, sheet: str) -> dict[str, Any]:
    with session_scope() as s:
        stmt = (
            select(Upload)
            .where(Upload.sha16 == sha16, Upload.sheet == sheet)
            .order_by(Upload.uploaded_at.desc())
            .limit(1)
        )
        rec = s.execute(stmt).scalars().first()
        if rec is None:
            raise HTTPException(404, f"No upload found for sha16={sha16} sheet={sheet}")
        summary = rec.summary or {}
        return {
            "sha16": sha16,
            "sheet": sheet,
            "relationships": summary.get("relationships", {}),
            "analysis_plan": summary.get("analysis_plan", []),
            "insights": summary.get("insights", {}),
            "aggregates": summary.get("aggregates", []),
        }


@router.put("/memory")
def update_memory(payload: MemoryUpdateRequest) -> dict[str, Any]:
    with session_scope() as s:
        stmt = (
            select(Upload)
            .where(Upload.sha16 == payload.sha16, Upload.sheet == payload.sheet)
            .order_by(Upload.uploaded_at.desc())
            .limit(1)
        )
        rec = s.execute(stmt).scalars().first()
        if rec is None:
            raise HTTPException(
                404, f"No upload found for sha16={payload.sha16} sheet={payload.sheet}"
            )
        summary = dict(rec.summary or {})
        if payload.relationships is not None:
            summary["relationships"] = payload.relationships
        if payload.analysis_plan is not None:
            summary["analysis_plan"] = payload.analysis_plan
        rec.summary = summary
        return {
            "sha16": payload.sha16,
            "sheet": payload.sheet,
            "relationships": summary.get("relationships", {}),
            "analysis_plan": summary.get("analysis_plan", []),
        }


def _ans_cache_key(q: str, keys: list[str]) -> str:
    m = hashlib.sha1()
    m.update(q.encode("utf-8"))
    for k in keys:
        m.update(k.encode("utf-8"))
    return f"dawn:ans:{m.hexdigest()}"


@router.get("/answer")
def rag_answer(q: str, k: int = 5) -> dict:
    hits = search(q, k=k)
    if not hits:
        return {
            "query": q,
            "answer": "I don’t have enough context to answer confidently yet. Try narrowing your question or indexing more data.",
            "sources": [],
        }

    # Cache by query + retrieved doc keys
    key_list = [h["key"] for h in hits]
    ck = _ans_cache_key(q, key_list)
    cached = redis_sync.get(ck)
    if cached:
        return json.loads(cached)

    ctx = format_context(hits)
    ans = llm_answer(q, ctx, hits)
    out: dict[str, Any] = {"query": q, "answer": ans, "sources": hits}
    redis_sync.setex(ck, 900, json.dumps(out))  # 15-minute TTL
    return out


@router.get("/ping")
def rag_ping() -> dict:
    try:
        redis_sync.ft("dawn:rag:index").info()
        ok = True
    except Exception:
        ok = False
    return {"index_ready": ok}


@router.post("/reset_index")
def rag_reset_index() -> dict:
    with contextlib.suppress(ResponseError):
        redis_sync.ft("dawn:rag:index").dropindex(delete_documents=False)
    # touching the index is handled lazily by _ensure_index on next upsert/search
    # do a no-op ensure to trigger create
    try:
        from app.core.rag import _ensure_index as _ei  # type: ignore

        _ei(redis_sync)
        ok = True
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": ok}
