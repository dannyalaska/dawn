from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import session_scope
from app.core.models import Upload


def _xlsx_bytes() -> bytes:
    df = pd.DataFrame(
        {
            "Date": ["2025-10-01", "2025-10-02", "2025-10-03"],
            "Client": ["Client A", "Client B", "Client A"],
            "Category": ["Login", "Billing", "Login"],
            "Severity": ["P1", "P2", "P3"],
        }
    )
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    return buf.getvalue()


@pytest.fixture
def client():
    from app.api.server import app

    return TestClient(app)


def test_rag_index_saves_summary_and_chunks(client, monkeypatch):
    captured: dict[str, Any] = {}

    def fake_upsert(chunks):
        captured["chunks"] = chunks
        return len(chunks)

    monkeypatch.setattr("app.api.rag.upsert_chunks", fake_upsert)

    content = _xlsx_bytes()
    files = {
        "file": (
            "test.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post("/rag/index_excel", files=files)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["rows"] == 3
    summary = payload["summary"]
    assert "Dataset summary" in summary["text"]
    # metrics should include Category counts
    metric_names = {m["type"] for m in summary["metrics"]}
    assert "value_counts" in metric_names
    top_metric = next(
        m
        for m in summary["metrics"]
        if m["type"] == "value_counts" and m["column"].lower() == "category"
    )
    assert top_metric["values"][0]["label"] == "Login"

    # Summary chunk should exist (row_index == -1)
    assert captured["chunks"][0].row_index == -1

    with session_scope() as s:
        rec = s.execute(
            select(Upload).filter_by(sha16=payload["sha16"], sheet="Sheet1")
        ).scalar_one_or_none()
        assert rec is not None
        assert rec.summary is not None
        assert rec.summary["metrics"][0]["values"]


def test_rag_query_and_answer(client, monkeypatch):
    fake_hits = [
        {
            "key": "1",
            "text": "Category: Login | Count: 10",
            "source": "test.xlsx:Sheet1",
            "row_index": -1,
            "score": 0.2,
        }
    ]

    monkeypatch.setattr("app.api.rag.search", lambda q, k=5: fake_hits)
    monkeypatch.setattr("app.api.rag.format_context", lambda hits: "context text")
    monkeypatch.setattr(
        "app.api.rag.llm_answer", lambda q, ctx, hits: "Login has the most tickets."
    )

    query_resp = client.get("/rag/query", params={"q": "test", "k": 5})
    assert query_resp.status_code == 200
    query_json = query_resp.json()
    assert query_json["sources"][0]["row_index"] == -1

    answer_resp = client.get("/rag/answer", params={"q": "test", "k": 5})
    assert answer_resp.status_code == 200
    answer_json = answer_resp.json()
    assert "Login has the most tickets" in answer_json["answer"]


def test_rag_chat_appends_history(client, monkeypatch):
    fake_hits = [
        {
            "key": "1",
            "text": "Summary chunk",
            "source": "demo:Sheet1",
            "row_index": -1,
            "score": 0.1,
        }
    ]
    monkeypatch.setattr("app.api.rag.search", lambda q, k=12: fake_hits)
    monkeypatch.setattr("app.api.rag.format_context", lambda hits, limit_chars=2500: "ctx")
    monkeypatch.setattr("app.api.rag.llm_answer", lambda q, ctx, hits: f"Answer to {q}")

    resp = client.post(
        "/rag/chat",
        json={
            "messages": [
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
                {"role": "user", "content": "Second question"},
            ],
            "k": 12,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["messages"][-1]["role"] == "assistant"
    assert "Answer to Second question" in data["messages"][-1]["content"]
