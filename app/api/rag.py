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
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import ResponseError
from sqlalchemy import select

from app.core.auth import CurrentUser
from app.core.chat_graph import run_chat
from app.core.db import session_scope
from app.core.excel.summary import summarize_dataframe
from app.core.limits import SizeLimitError, read_upload_bytes
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
    *,
    current_user: CurrentUser,
) -> dict:
    try:
        data = await read_upload_bytes(file, label="RAG Excel index")
    except SizeLimitError as exc:
        raise HTTPException(413, str(exc)) from exc
    name = file.filename or "upload.xlsx"
    return await run_in_threadpool(
        _index_excel_sync,
        data,
        name,
        sheet,
        chunk_max_chars,
        chunk_overlap,
        current_user.id,
    )


def _index_excel_sync(
    data: bytes,
    name: str,
    sheet: str | None,
    chunk_max_chars: int,
    chunk_overlap: int,
    user_id: int,
) -> dict[str, Any]:
    try:
        xl = pd.ExcelFile(BytesIO(data))
    except Exception as exc:
        raise HTTPException(400, f"Failed to read Excel: {exc}") from exc

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
    except Exception as exc:
        raise HTTPException(400, f"Failed to read sheet '{actual_sheet}': {exc}") from exc

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

    def _infer_dataset_tags() -> list[str]:
        tags: set[str] = set()
        names = [cs.name.lower() for cs in column_summaries]
        if any("lat" in n for n in names) and any(
            kw in n for kw in ("lon", "lng", "long") for n in names
        ):
            tags.add("geospatial")
        if any("address" in n or "city" in n or "zip" in n for n in names):
            tags.add("location")
        if any("date" in n or "time" in n or "timestamp" in n for n in names):
            tags.add("temporal")
        if any("amount" in n or "revenue" in n or "cost" in n for n in names):
            tags.add("financial")
        if any("status" in n or "state" in n for n in names):
            tags.add("status-tracking")
        if any("ticket" in n for n in names):
            tags.add("records")
        return sorted(tags)

    dataset_tags = _infer_dataset_tags()

    chunks: list[Chunk] = []
    src = f"{name}:{actual_sheet}"
    if combined_summary:
        for piece in simple_chunker(combined_summary, max_chars=900, overlap=0):
            chunks.append(
                Chunk(
                    text=f"Summary for {src}: {piece}",
                    source=f"{src}:summary",
                    row_index=-1,
                    chunk_type="summary",
                    metadata={"tags": dataset_tags},
                )
            )

    for column in column_summaries:
        details: list[str] = [f"Column {column.name} (dtype {column.dtype})."]
        if column.top_values:
            sample = ", ".join(f"{label} ({count})" for label, count in column.top_values[:5])
            details.append(f"Top values: {sample}.")
        if column.stats:
            stats = ", ".join(f"{k}={v:.2f}" for k, v in column.stats.items())
            details.append(f"Stats: {stats}.")
        column_tags = dataset_tags + [f"column:{column.name.lower()}"]
        chunks.append(
            Chunk(
                text=" ".join(details),
                source=f"{src}:column:{column.name}",
                row_index=-1,
                chunk_type="column_profile",
                metadata={"column_name": column.name, "tags": column_tags, "dtype": column.dtype},
            )
        )

    for i, row in df_text.iterrows():
        row_text = " | ".join(f"{col}: {row[col]}" for col in df_text.columns)
        for piece in simple_chunker(row_text, max_chars=chunk_max_chars, overlap=chunk_overlap):
            chunks.append(
                Chunk(
                    text=piece,
                    source=src,
                    row_index=int(i),
                    chunk_type="sample_row",
                    metadata={"tags": dataset_tags},
                )
            )

    n = upsert_chunks(chunks, user_id=str(user_id))

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
        "tags": dataset_tags,
    }

    size_bytes = len(data)
    row_count = int(len(df_original))
    col_count = int(len(df_original.columns))

    with session_scope() as s:
        stmt = (
            select(Upload)
            .where(
                Upload.sha16 == digest,
                Upload.sheet == actual_sheet,
                Upload.user_id == user_id,
            )
            .order_by(Upload.uploaded_at.desc())
            .limit(1)
        )
        existing = s.execute(stmt).scalars().first()
        if existing:
            existing.summary = summary_payload
            existing.rows = row_count
            existing.cols = col_count
            existing.size_bytes = size_bytes
            existing.user_id = user_id
        else:
            s.add(
                Upload(
                    filename=name,
                    sheet=actual_sheet,
                    sha16=digest,
                    size_bytes=size_bytes,
                    rows=row_count,
                    cols=col_count,
                    user_id=user_id,
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
    notes: list[str] | None = None

    model_config = ConfigDict(populate_by_name=True)


@router.post("/chat")
def rag_chat(payload: ChatRequest, current_user: CurrentUser) -> dict[str, Any]:
    message_dicts = [msg.model_dump() for msg in payload.messages]
    try:
        result = run_chat(message_dicts, k=payload.k, user_id=str(current_user.id))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@router.get("/query")
def rag_query(q: str, *, k: int = 5, current_user: CurrentUser) -> dict:
    hits = search(q, k=k, user_id=str(current_user.id))
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
    source: str = FQuery(...),
    limit: int = FQuery(default=200, ge=1, le=500),
    *,
    current_user: CurrentUser,
) -> dict[str, Any]:
    source_clean = source.strip()
    if not source_clean:
        raise HTTPException(400, "source must be provided")
    notes = list_context_chunks(user_id=str(current_user.id), source=source_clean, limit=limit)
    return {
        "source": source_clean,
        "count": len(notes),
        "notes": notes,
        "chunks": notes,  # backwards compatibility for older clients
    }


@router.put("/context/{chunk_id}")
def update_context(
    chunk_id: str,
    payload: ContextUpdateRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "text cannot be empty")
    try:
        updated = update_context_chunk(str(current_user.id), chunk_id, text)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"updated": updated}


@router.post("/context/note")
def add_context(payload: ContextNoteRequest, current_user: CurrentUser) -> dict[str, Any]:
    source = payload.source.strip()
    text = payload.text.strip()
    if not source:
        raise HTTPException(400, "source cannot be empty")
    if not text:
        raise HTTPException(400, "text cannot be empty")
    created = add_manual_note(str(current_user.id), source, text)
    return {"created": created}


@router.get("/memory")
def get_memory(sha16: str, sheet: str, current_user: CurrentUser) -> dict[str, Any]:
    with session_scope() as s:
        stmt = (
            select(Upload)
            .where(
                Upload.sha16 == sha16,
                Upload.sheet == sheet,
                Upload.user_id == current_user.id,
            )
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
            "notes": summary.get("notes", []),
        }


@router.put("/memory")
def update_memory(payload: MemoryUpdateRequest, current_user: CurrentUser) -> dict[str, Any]:
    with session_scope() as s:
        stmt = (
            select(Upload)
            .where(
                Upload.sha16 == payload.sha16,
                Upload.sheet == payload.sheet,
                Upload.user_id == current_user.id,
            )
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
        if payload.notes is not None:
            summary["notes"] = payload.notes
        rec.summary = summary
        return {
            "sha16": payload.sha16,
            "sheet": payload.sheet,
            "relationships": summary.get("relationships", {}),
            "analysis_plan": summary.get("analysis_plan", []),
            "notes": summary.get("notes", []),
        }


def _ans_cache_key(q: str, keys: list[str], user_id: str) -> str:
    m = hashlib.sha1()
    m.update(q.encode("utf-8"))
    for k in keys:
        m.update(k.encode("utf-8"))
    m.update(user_id.encode("utf-8"))
    return f"dawn:ans:{user_id}:{m.hexdigest()}"


@router.get("/answer")
def rag_answer(q: str, *, k: int = 5, current_user: CurrentUser) -> dict:
    user_id = str(current_user.id)
    hits = search(q, k=k, user_id=user_id)
    if not hits:
        return {
            "query": q,
            "answer": "I don’t have enough context to answer confidently yet. Try narrowing your question or indexing more data.",
            "sources": [],
        }

    key_list = [h["key"] for h in hits]
    ck = _ans_cache_key(q, key_list, user_id)
    cached = redis_sync.get(ck)
    if cached:
        return json.loads(cached)

    try:
        result = run_chat([{"role": "user", "content": q}], k=k, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    response: dict[str, Any] = {
        "query": q,
        "answer": result.get("answer", ""),
        "sources": result.get("sources", []),
    }
    redis_sync.setex(ck, 900, json.dumps(response))
    return response


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
