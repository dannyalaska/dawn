from __future__ import annotations

import numpy as np

from app.core import rag
from app.core.rag import format_context, simple_chunker


def test_simple_chunker_respects_overlap():
    text = " ".join(str(i) for i in range(200))
    parts = simple_chunker(text, max_chars=40, overlap=10)
    assert len(parts) > 1
    for idx in range(1, len(parts)):
        # Ensure overlap by checking prefix equality
        assert parts[idx - 1][-10:] == parts[idx][:10]


def test_format_context_limits_length():
    chunks = [
        {"source": "file:Sheet1", "row_index": 1, "text": "A" * 1000},
        {"source": "file:Sheet1", "row_index": 2, "text": "B" * 1000},
    ]
    formatted = format_context(chunks, limit_chars=1200)
    assert "[1]" in formatted
    assert "[2]" not in formatted  # second chunk trimmed because of limit


def test_list_context_chunks_handles_binary_embeddings(monkeypatch):
    class _FakeRedis:
        def __init__(self) -> None:
            key = rag._doc_key("abc123")
            self._store = {
                key: {
                    "text": "Original chunk",
                    "source": "demo:Sheet1",
                    "row_index": "5",
                    "type": "excel",
                    rag.VEC_FIELD: np.zeros(384, dtype=np.float32).tobytes(),
                }
            }

        def scan_iter(self, match: str):
            prefix = match.rstrip("*")
            return [key for key in self._store if key.startswith(prefix)]

        def hmget(self, key: str, *fields: str):
            data = self._store.get(key, {})
            return [data.get(field) for field in fields]

    fake = _FakeRedis()
    monkeypatch.setattr(rag, "redis_sync", fake)

    chunks = rag.list_context_chunks(source="demo:Sheet1", limit=10)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "Original chunk"
    assert chunks[0]["type"] == "excel"
