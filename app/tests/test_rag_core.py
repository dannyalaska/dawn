from __future__ import annotations

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
