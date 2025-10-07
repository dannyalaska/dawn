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
from pydantic import BaseModel, Field
from redis.exceptions import ResponseError
from sqlalchemy import select

from app.core.db import session_scope
from app.core.excel.summary import summarize_dataframe
from app.core.llm import answer as llm_answer
from app.core.models import Upload
from app.core.rag import Chunk, format_context, search, simple_chunker, upsert_chunks
from app.core.redis_client import redis_sync

router = APIRouter(prefix="/rag", tags=["rag"])

# Avoid Ruff B008: evaluate File(...) at import time, then use in signature
file_param: File = File(...)


@router.post("/index_excel")
async def index_excel(
    file: UploadFile = file_param,
    sheet: str | None = FQuery(default=None),
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

    try:
        df = xl.parse(actual_sheet)
    except Exception as e:
        raise HTTPException(400, f"Failed to read sheet '{actual_sheet}': {e}") from e

    digest = hashlib.sha256(data).hexdigest()[:16]
    df = df.fillna("").astype(str)
    summary_text, column_summaries, dataset_metrics = summarize_dataframe(df)
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
    for i, row in df.iterrows():
        row_text = " | ".join(f"{col}: {row[col]}" for col in df.columns)
        for piece in simple_chunker(row_text, max_chars=600, overlap=80):
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
    }

    size_bytes = len(data)
    row_count = int(len(df))
    col_count = int(len(df.columns))

    with session_scope() as s:
        existing = s.execute(
            select(Upload).where(Upload.sha16 == digest, Upload.sheet == actual_sheet)
        ).scalar_one_or_none()
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
    }


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    k: int = Field(default=12, ge=1, le=50)


@router.post("/chat")
def rag_chat(payload: ChatRequest) -> dict[str, Any]:
    if payload.messages[-1].role != "user":
        raise HTTPException(400, "Last message must be from the user.")

    question = payload.messages[-1].content
    hits = search(question, k=payload.k)
    ctx = format_context(hits, limit_chars=2500)

    history_lines = [f"{msg.role.capitalize()}: {msg.content}" for msg in payload.messages[:-1]]
    if history_lines:
        history_block = "\n".join(history_lines)
        ctx = f"Conversation so far:\n{history_block}\n\nRetrieved data:\n{ctx}"

    answer_text = (
        llm_answer(question, ctx, hits)
        if hits
        else ("I don't have enough context yet. Try indexing more data or restating the question.")
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
