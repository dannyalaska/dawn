from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore, VectorStoreRetriever
from langchain_huggingface import HuggingFaceEmbeddings
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
from redis.exceptions import ResponseError

from app.core.redis_client import redis_binary, redis_sync

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim
INDEX_NAME = "dawn:rag:index"
PREFIX = "dawn:rag:doc:"
VEC_FIELD = "embedding"
LOGGER = logging.getLogger(__name__)
_VECTOR_INDEX_SUPPORTED: bool | None = None
_NO_SEARCH_WARNING_EMITTED = False


@dataclass
class Chunk:
    text: str
    source: str
    row_index: int
    chunk_type: str = "excel"
    metadata: dict[str, Any] | None = None


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


def _doc_key(user_id: str, docid: str) -> str:
    return f"{PREFIX}{user_id}:{docid}"


def _redis_supports_vector_index(redis: Redis) -> bool:
    global _VECTOR_INDEX_SUPPORTED
    if _VECTOR_INDEX_SUPPORTED is not None:
        return _VECTOR_INDEX_SUPPORTED
    try:
        redis.execute_command("FT._LIST")
        _VECTOR_INDEX_SUPPORTED = True
    except ResponseError as exc:
        message = str(exc).lower()
        if "unknown command" in message or "err unknown command" in message:
            _VECTOR_INDEX_SUPPORTED = False
        else:
            _VECTOR_INDEX_SUPPORTED = True
    except Exception:
        _VECTOR_INDEX_SUPPORTED = False
    return bool(_VECTOR_INDEX_SUPPORTED)


def _ensure_index(redis: Redis, dim: int = 384) -> None:
    global _NO_SEARCH_WARNING_EMITTED
    if not _redis_supports_vector_index(redis):
        if not _NO_SEARCH_WARNING_EMITTED:
            LOGGER.warning(
                "Redis instance is missing RediSearch (FT.*) commands. Falling back to local "
                "similarity search; install redis-stack for best performance."
            )
            _NO_SEARCH_WARNING_EMITTED = True
        return
    required_fields = {
        "text",
        "source",
        "type",
        "row_index",
        "user_id",
        "tags",
        "metadata",
        "column_name",
        VEC_FIELD,
    }
    needs_rebuild = False

    try:
        info = redis.ft(INDEX_NAME).info()
        attributes = info.get("attributes", [])
        parsed: dict[str, dict[str, Any]] = {}
        for attr in attributes:
            data = {attr[i]: attr[i + 1] for i in range(0, len(attr), 2)}
            identifier = data.get("identifier")
            if identifier:
                parsed[str(identifier)] = data
        missing = required_fields.difference(parsed.keys())
        if missing:
            needs_rebuild = True
        else:
            vec_meta = parsed.get(VEC_FIELD, {})
            try:
                current_dim = int(vec_meta.get("dim", 0))
            except (TypeError, ValueError):
                current_dim = 0
            if current_dim != dim:
                needs_rebuild = True
    except Exception:  # noqa: BLE001
        needs_rebuild = True

    if not needs_rebuild:
        return

    with contextlib.suppress(ResponseError):
        redis.ft(INDEX_NAME).dropindex(delete_documents=False)

    schema = [
        TextField("text"),
        TextField("source"),
        TagField("type"),
        NumericField("row_index"),
        TagField("user_id"),
        TagField("tags"),
        TextField("column_name"),
        TextField("metadata"),
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
    try:
        redis.ft(INDEX_NAME).create_index(fields=schema, definition=definition)
    except ResponseError as exc:
        message = str(exc).lower()
        if "unknown command" in message or "err unknown command" in message:
            _VECTOR_INDEX_SUPPORTED = False
            if not _NO_SEARCH_WARNING_EMITTED:
                LOGGER.warning(
                    "Redis instance rejected FT.CREATE. Falling back to local similarity search; "
                    "install redis-stack for vector indexing."
                )
                _NO_SEARCH_WARNING_EMITTED = True
            return
        raise


def _escape_tag(value: str) -> str:
    return value.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,")


@lru_cache(maxsize=1)
def _get_embeddings() -> Embeddings:
    return HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Expose embeddings for legacy callers (returns float32 array)."""

    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    embeddings = _get_embeddings().embed_documents(texts)
    return np.array(embeddings, dtype=np.float32)


class RedisHashVectorStore(VectorStore):
    """LangChain-compatible vector store that wraps Dawn's Redis schema."""

    def __init__(self, redis: Redis, embeddings: Embeddings, *, dim: int = 384) -> None:
        self.redis = redis
        self._embeddings = embeddings
        self.dim = dim
        _ensure_index(redis, dim)

    # ------------------------------------------------------------------
    # VectorStore API
    # ------------------------------------------------------------------
    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Iterable[dict[str, Any]] | None = None,
        ids: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> list[str]:  # type: ignore[override]
        text_list = list(texts)
        if not text_list:
            return []
        metadata_list = list(metadatas or ({} for _ in text_list))
        if len(metadata_list) != len(text_list):
            raise ValueError("Length of metadatas must match texts")

        id_list = list(ids or ())
        if id_list and len(id_list) != len(text_list):
            raise ValueError("Length of ids must match texts")
        if not id_list:
            id_list = [hashlib.sha1(t.encode("utf-8")).hexdigest()[:16] for t in text_list]

        vectors = embed_texts(text_list)
        pipe = self.redis.pipeline()

        for text, metadata, doc_id, vector in zip(
            text_list, metadata_list, id_list, vectors, strict=False
        ):
            meta = dict(metadata or {})
            user_id = str(meta.get("user_id", "default"))
            key = _doc_key(user_id, doc_id)
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags_list = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                tags_list = [str(t) for t in tags]
            stored_metadata = {
                "source": meta.get("source") or "",
                "row_index": int(meta.get("row_index", -1) or -1),
                "type": meta.get("chunk_type") or meta.get("type", "excel"),
                "id": doc_id,
                "user_id": user_id,
                "tags": tags_list,
            }
            if "column_name" in meta:
                stored_metadata["column_name"] = meta["column_name"]
            if "dtype" in meta:
                stored_metadata["dtype"] = meta["dtype"]
            mapping: dict[str | bytes, bytes | float | int | str] = {
                "text": text,
                "source": stored_metadata["source"],
                "row_index": stored_metadata["row_index"],
                "type": stored_metadata["type"],
                "metadata": json.dumps(stored_metadata),
                "user_id": user_id,
                "tags": ",".join(tags_list) if tags_list else "",
                VEC_FIELD: np.asarray(vector, dtype=np.float32).tobytes(),
            }
            column_name = stored_metadata.get("column_name")
            if column_name:
                mapping["column_name"] = column_name
            pipe.hset(key, mapping=mapping)

        pipe.execute()
        return id_list

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Document]:  # type: ignore[override]
        return [doc for doc, _ in self.similarity_search_with_score(query, k=k, filter=filter)]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        query_vec = np.array(self._embeddings.embed_query(query), dtype=np.float32)
        return self.similarity_search_by_vector_with_score(query_vec.tolist(), k=k, filter=filter)

    def similarity_search_by_vector_with_score(
        self,
        embedding: Sequence[float],
        k: int = 4,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        vec = np.array(embedding, dtype=np.float32)
        if vec.size != self.dim:
            raise ValueError(f"Embedding dim mismatch: expected {self.dim}, got {vec.size}")

        if not _redis_supports_vector_index(self.redis):
            return self._fallback_similarity_search(vec, k=k, filter=filter)

        _ensure_index(self.redis, self.dim)
        filter_clause = "*"
        if filter and filter.get("user_id"):
            user_tag = _escape_tag(str(filter["user_id"]))
            filter_clause = f"@user_id:{{{user_tag}}}"
        query = (
            Query(f"{filter_clause}=>[KNN {k} @{VEC_FIELD} $vec AS score]")
            .return_fields(
                "text",
                "source",
                "row_index",
                "type",
                "metadata",
                "score",
                "tags",
                "column_name",
                "user_id",
            )
            .sort_by("score")
            .dialect(2)
        )
        query_params: dict[str, Any] = {"vec": vec.tobytes()}
        raw = self.redis.ft(INDEX_NAME).search(query, query_params=query_params)

        results: list[tuple[Document, float]] = []
        for row in raw.docs:
            metadata: dict[str, Any]
            try:
                metadata = json.loads(row.metadata) if getattr(row, "metadata", None) else {}
            except Exception:  # noqa: BLE001
                metadata = {}
            metadata.setdefault("source", getattr(row, "source", None))
            metadata.setdefault("row_index", int(getattr(row, "row_index", -1) or -1))
            metadata.setdefault("type", getattr(row, "type", "excel"))
            metadata.setdefault("user_id", getattr(row, "user_id", None))
            if "id" not in metadata and getattr(row, "id", None):
                metadata["id"] = str(row.id).removeprefix(PREFIX)
            if getattr(row, "tags", None) and not metadata.get("tags"):
                metadata["tags"] = [t for t in str(row.tags).split(",") if t]
            if getattr(row, "column_name", None) and "column_name" not in metadata:
                metadata["column_name"] = row.column_name

            doc = Document(page_content=row.text, metadata=metadata)
            results.append((doc, float(row.score)))
        return results

    def _fallback_similarity_search(
        self, vec: np.ndarray, k: int, filter: dict[str, Any] | None = None
    ) -> list[tuple[Document, float]]:
        user_filter = str(filter.get("user_id")) if filter and filter.get("user_id") else None
        pattern = f"{PREFIX}{user_filter}:*" if user_filter else f"{PREFIX}*"
        results: list[tuple[Document, float]] = []
        vec_norm = float(np.linalg.norm(vec)) or 1e-12

        def _decode(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, bytes):
                try:
                    return value.decode("utf-8")
                except Exception:
                    return value.decode("utf-8", errors="ignore")
            return str(value)

        for key in self.redis.scan_iter(match=pattern):
            (
                text_raw,
                metadata_raw,
                row_raw,
                type_raw,
                tags_raw,
                source_raw,
                column_name_raw,
                vec_raw,
            ) = redis_binary.hmget(
                key,
                "text",
                "metadata",
                "row_index",
                "type",
                "tags",
                "source",
                "column_name",
                VEC_FIELD,
            )
            text_val = _decode(text_raw)
            if not text_val or not vec_raw:
                continue
            chunk_vec = np.frombuffer(vec_raw, dtype=np.float32)
            if chunk_vec.size != self.dim:
                continue
            chunk_norm = float(np.linalg.norm(chunk_vec)) or 1e-12
            cosine = float(np.dot(vec, chunk_vec) / (vec_norm * chunk_norm))
            score = 1 - cosine

            metadata: dict[str, Any] = {}
            metadata_str = _decode(metadata_raw)
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                except Exception:  # noqa: BLE001
                    metadata = {}
            source_val = _decode(source_raw)
            if source_val and not metadata.get("source"):
                metadata["source"] = source_val
            if "row_index" in metadata:
                try:
                    metadata["row_index"] = int(metadata["row_index"])
                except Exception:
                    metadata["row_index"] = -1
            else:
                row_str = _decode(row_raw)
                metadata["row_index"] = int(row_str or -1)
            type_val = _decode(type_raw)
            metadata["type"] = metadata.get("type") or type_val or "excel"
            if tags_raw and not metadata.get("tags"):
                tags_val = _decode(tags_raw) or ""
                metadata["tags"] = [t for t in tags_val.split(",") if t]
            column_name = _decode(column_name_raw)
            if column_name and "column_name" not in metadata:
                metadata["column_name"] = column_name
            raw_key = key.decode() if isinstance(key, bytes | bytearray) else str(key)
            doc_id = metadata.get("id")
            if not doc_id:
                doc_id = raw_key.rsplit(":", 1)[-1]
                metadata["id"] = doc_id
            doc = Document(page_content=text_val, metadata=metadata)
            results.append((doc, score))

        results.sort(key=lambda item: item[1])
        return results[:k]

    def as_retriever(self, **kwargs: Any) -> VectorStoreRetriever:  # type: ignore[override]
        return VectorStoreRetriever(vectorstore=self, **kwargs)

    @classmethod
    def from_texts(
        cls,
        texts: list[str],
        embedding: Embeddings,
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        redis_client: Redis | None = None,
        **kwargs: Any,
    ) -> RedisHashVectorStore:
        store = cls(redis_client or redis_sync, embedding, **kwargs)
        store.add_texts(texts, metadatas=metadatas, ids=ids)
        return store

    @property
    def embeddings(self) -> Embeddings:  # type: ignore[override]
        return self._embeddings


@lru_cache(maxsize=1)
def _get_vector_store() -> RedisHashVectorStore:
    return RedisHashVectorStore(redis_sync, _get_embeddings())


def get_retriever(k: int = 6) -> VectorStoreRetriever:
    return _get_vector_store().as_retriever(search_kwargs={"k": k})


def upsert_chunks(chunks: list[Chunk], *, user_id: str = "default") -> int:
    if not chunks:
        return 0
    texts = [c.text for c in chunks]
    metadatas: list[dict[str, Any]] = []
    ids: list[str] = []
    for chunk in chunks:
        metadata = {
            "source": chunk.source,
            "row_index": chunk.row_index,
            "chunk_type": chunk.chunk_type,
            "user_id": user_id,
        }
        if chunk.metadata:
            metadata.update(chunk.metadata)
        metadatas.append(metadata)
        ids.append(
            hashlib.sha1((user_id + chunk.source + chunk.text).encode("utf-8")).hexdigest()[:16]
        )
    _get_vector_store().add_texts(texts=texts, metadatas=metadatas, ids=ids)
    return len(chunks)


def search(query_text: str, k: int = 5, user_id: str = "default") -> list[dict[str, Any]]:
    results = _get_vector_store().similarity_search_with_score(
        query_text, k=k, filter={"user_id": user_id}
    )
    hits: list[dict[str, Any]] = []
    for doc, score in results:
        metadata = dict(doc.metadata)
        doc_id = metadata.get("id")
        if not doc_id:
            doc_id = hashlib.sha1(
                (user_id + metadata.get("source", "") + doc.page_content).encode("utf-8")
            ).hexdigest()[:16]
            metadata["id"] = doc_id
        hits.append(
            {
                "key": _doc_key(user_id, doc_id),
                "id": doc_id,
                "text": doc.page_content,
                "source": metadata.get("source"),
                "row_index": metadata.get("row_index", -1),
                "type": metadata.get("type", "excel"),
                "tags": metadata.get("tags", []),
                "column_name": metadata.get("column_name"),
                "score": score,
            }
        )
    return hits


def format_context(chunks: list[dict[str, Any]], limit_chars: int = 2500) -> str:
    buf: list[str] = []
    total = 0
    for i, c in enumerate(chunks, 1):
        source = c.get("source", "?")
        row = c.get("row_index", "?")
        text = c.get("text", "")
        segment = f"[{i}] source={source} row={row}\n{text}\n"
        if total + len(segment) > limit_chars:
            break
        buf.append(segment)
        total += len(segment)
    return "\n".join(buf)


def list_context_chunks(
    *, user_id: str, source: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    pattern = f"{PREFIX}{user_id}:*"
    chunks: list[dict[str, Any]] = []
    for key in redis_sync.scan_iter(match=pattern):
        (
            text_val,
            source_val,
            metadata_raw,
            row_raw,
            type_val,
            tags_raw,
        ) = redis_sync.hmget(
            key,
            "text",
            "source",
            "metadata",
            "row_index",
            "type",
            "tags",
        )
        if not any([text_val, source_val, metadata_raw, row_raw, type_val]):
            continue

        metadata: dict[str, Any] = {}
        if metadata_raw:
            try:
                metadata = json.loads(metadata_raw)
            except Exception:  # noqa: BLE001
                metadata = {}

        raw_source = metadata.get("source") or source_val or ""
        if source and raw_source != source:
            continue

        doc_id = metadata.get("id") or key[len(f"{PREFIX}{user_id}:") :]
        tags = metadata.get("tags")
        if not tags and tags_raw:
            if isinstance(tags_raw, str):
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            else:
                tags = tags_raw

        row_index_val = metadata.get("row_index", row_raw or -1)
        if isinstance(row_index_val, str):
            try:
                row_index_val = int(row_index_val)
            except ValueError:
                row_index_val = -1

        chunk_type = metadata.get("type") or type_val or "excel"

        chunks.append(
            {
                "id": metadata.get("id", doc_id),
                "text": text_val or "",
                "source": raw_source,
                "row_index": int(row_index_val or -1),
                "type": chunk_type,
                "tags": tags or [],
            }
        )
        if len(chunks) >= limit:
            break
    chunks.sort(key=lambda c: (c.get("type") != "note", c.get("row_index", 0), c.get("id", "")))
    return chunks


def update_context_chunk(user_id: str, doc_id: str, new_text: str) -> dict[str, Any]:
    key = _doc_key(user_id, doc_id)
    metadata_raw, source_val, row_raw, type_val = redis_sync.hmget(
        key, "metadata", "source", "row_index", "type"
    )
    if metadata_raw is None and source_val is None and row_raw is None and type_val is None:
        raise KeyError(f"Chunk {doc_id!r} not found")

    metadata: dict[str, Any] = {}
    if metadata_raw:
        try:
            metadata = json.loads(metadata_raw)
        except Exception:  # noqa: BLE001
            metadata = {}
    metadata["id"] = doc_id
    metadata["user_id"] = user_id
    metadata.setdefault("source", source_val)
    metadata.setdefault("row_index", int(row_raw or -1))
    metadata.setdefault("type", type_val or "excel")

    vec = embed_texts([new_text])[0]
    redis_sync.hset(
        key,
        mapping={
            "text": new_text,
            "metadata": json.dumps(metadata),
            VEC_FIELD: np.asarray(vec, dtype=np.float32).tobytes(),
        },
    )

    return {
        "id": doc_id,
        "text": new_text,
        "source": metadata.get("source"),
        "row_index": metadata.get("row_index", -1),
        "type": metadata.get("type", "excel"),
    }


def add_manual_note(user_id: str, source: str, note: str) -> dict[str, Any]:
    chunk = Chunk(text=note, source=source, row_index=-1, chunk_type="note")
    upsert_chunks([chunk], user_id=user_id)
    doc_id = hashlib.sha1((user_id + chunk.source + chunk.text).encode("utf-8")).hexdigest()[:16]
    key = _doc_key(user_id, doc_id)
    stored = redis_sync.hgetall(key)
    metadata_raw = stored.get("metadata")
    tags: list[str] = []
    if metadata_raw:
        try:
            meta = json.loads(metadata_raw)
            tags = meta.get("tags", []) if isinstance(meta.get("tags"), list) else tags
        except Exception:  # noqa: BLE001
            tags = []
    return {
        "id": doc_id,
        "text": stored.get("text", note),
        "source": stored.get("source", source),
        "row_index": -1,
        "type": "note",
        "tags": tags,
    }
