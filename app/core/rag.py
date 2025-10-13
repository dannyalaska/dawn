from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
from redis import Redis  # type: ignore[import-untyped]
from redis.commands.search.field import (  # type: ignore[import-untyped]
    NumericField,
    TagField,
    TextField,
    VectorField,
)
from redis.commands.search.index_definition import (  # type: ignore[import-untyped]
    IndexDefinition,
    IndexType,
)
from redis.commands.search.query import Query  # type: ignore[import-untyped]
from sentence_transformers import SentenceTransformer

from app.core.redis_client import redis_sync

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim
INDEX_NAME = "dawn:rag:index"
PREFIX = "dawn:rag:doc:"  # HASH key prefix for chunks
VEC_FIELD = "embedding"  # field name storing the vector bytes

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    model = _get_model()
    arr = np.array(model.encode(texts, normalize_embeddings=True), dtype=np.float32)  # (N,384)
    return arr


def _ensure_index(redis: Redis, dim: int = 384) -> None:
    try:
        redis.ft(INDEX_NAME).info()
        return
    except Exception:
        pass
    schema = [
        TextField("text"),
        TextField("source"),
        TagField("type"),
        NumericField("row_index"),
        VectorField(
            VEC_FIELD,
            "HNSW",
            {
                "TYPE": "FLOAT32",
                "DIM": dim,
                "DISTANCE_METRIC": "COSINE",
                "M": 16,
                "EF_CONSTRUCTION": 200,
            },
        ),
    ]
    definition = IndexDefinition(prefix=[PREFIX], index_type=IndexType.HASH)
    redis.ft(INDEX_NAME).create_index(fields=schema, definition=definition)


def _doc_key(docid: str) -> str:
    return f"{PREFIX}{docid}"


@dataclass
class Chunk:
    text: str
    source: str
    row_index: int
    chunk_type: str = "excel"


def simple_chunker(text: str, *, max_chars: int = 800, overlap: int = 120) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    i = 0
    while i < len(text):
        part = text[i : i + max_chars]
        out.append(part)
        if i + max_chars >= len(text):
            break
        i += max_chars - overlap
    return out


def upsert_chunks(chunks: list[Chunk]) -> int:
    if not chunks:
        return 0
    _ensure_index(redis_sync, 384)
    texts = [c.text for c in chunks]
    vecs = embed_texts(texts)  # (N,384) float32
    pipe = redis_sync.pipeline()
    for c, v in zip(chunks, vecs, strict=False):
        h = hashlib.sha1((c.source + c.text).encode("utf-8")).hexdigest()[:16]
        key = _doc_key(h)
        pipe.hset(
            key,
            mapping={
                "text": c.text,
                "source": c.source,
                "type": c.chunk_type,
                "row_index": c.row_index,
                VEC_FIELD: v.tobytes(),
            },
        )
    pipe.execute()
    return len(chunks)


def search(query_text: str, k: int = 5) -> list[dict[str, Any]]:
    _ensure_index(redis_sync, 384)
    qvec = embed_texts([query_text])[0].tobytes()
    q = (
        Query(f"*=>[KNN {k} @{VEC_FIELD} $vec AS score]")
        .return_fields("text", "source", "row_index", "score")
        .sort_by("score")
        .dialect(2)
    )
    res = redis_sync.ft(INDEX_NAME).search(q, query_params={"vec": qvec})
    hits: list[dict[str, Any]] = []
    for d in res.docs:
        hits.append(
            {
                "key": d.id,
                "text": d.text,
                "source": d.source,
                "row_index": int(d.row_index),
                "score": float(d.score),
            }
        )
    return hits


def format_context(chunks: list[dict[str, Any]], limit_chars: int = 2500) -> str:
    buf: list[str] = []
    total = 0
    for i, c in enumerate(chunks, 1):
        s = f"[{i}] source={c['source']} row={c['row_index']}\n{c['text']}\n"
        if total + len(s) > limit_chars:
            break
        buf.append(s)
        total += len(s)
    return "\n".join(buf)


def list_context_chunks(source: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for key in redis_sync.scan_iter(match=f"{PREFIX}*"):
        text_val, source_val, row_raw, chunk_type = redis_sync.hmget(
            key, "text", "source", "row_index", "type"
        )
        if text_val is None and source_val is None:
            continue
        chunk_source = source_val if source_val is not None else None
        if source and chunk_source != source:
            continue
        doc_id = key[len(PREFIX) :]
        chunk_kind = chunk_type or "excel"
        try:
            row_index = int(row_raw) if row_raw is not None else -1
        except Exception:  # noqa: BLE001
            row_index = -1
        chunks.append(
            {
                "id": doc_id,
                "text": text_val or "",
                "source": chunk_source,
                "row_index": row_index,
                "type": chunk_kind,
            }
        )
        if len(chunks) >= limit:
            break
    chunks.sort(key=lambda c: (c.get("type") != "note", c.get("row_index", 0), c.get("id", "")))
    return chunks


def update_context_chunk(doc_id: str, new_text: str) -> dict[str, Any]:
    key = _doc_key(doc_id)
    source_val, row_raw, chunk_type = redis_sync.hmget(key, "source", "row_index", "type")
    if source_val is None and row_raw is None and chunk_type is None:
        msg = f"Chunk {doc_id!r} not found"
        raise KeyError(msg)
    vec = embed_texts([new_text])[0].tobytes()
    redis_sync.hset(
        key,
        mapping={
            "text": new_text,
            VEC_FIELD: vec,
        },
    )
    try:
        row_index = int(row_raw) if row_raw is not None else -1
    except Exception:  # noqa: BLE001
        row_index = -1
    return {
        "id": doc_id,
        "text": new_text,
        "source": source_val,
        "row_index": row_index,
        "type": chunk_type or "excel",
    }


def add_manual_note(source: str, note: str) -> dict[str, Any]:
    chunk = Chunk(text=note, source=source, row_index=-1, chunk_type="note")
    upsert_chunks([chunk])
    doc_id = hashlib.sha1((chunk.source + chunk.text).encode("utf-8")).hexdigest()[:16]
    key = _doc_key(doc_id)
    text_val, source_val, row_val, type_val = redis_sync.hmget(
        key, "text", "source", "row_index", "type"
    )
    return {
        "id": doc_id,
        "text": text_val or "",
        "source": source_val,
        "row_index": -1,
        "type": type_val or "note",
    }
