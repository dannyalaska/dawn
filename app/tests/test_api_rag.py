from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
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


def _resolver_xlsx_bytes() -> bytes:
    df = pd.DataFrame(
        {
            "Assigned_To": ["Alex", "Priya", "Alex", "Sam"],
            "Resolution_Time_Hours": [12, 5, 18, 7],
            "Ticket_ID": ["T1", "T2", "T3", "T4"],
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
    assert summary.get("insights")
    assert summary.get("relationships")
    assert summary.get("analysis_plan")

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


def test_context_endpoints(client, monkeypatch):
    import app.core.rag as rag_module

    fake_redis = rag_module.redis_sync
    doc_id = "manual0001"
    key = rag_module._doc_key(doc_id)
    fake_redis.hset(
        key,
        mapping={
            "text": "Original context",
            "source": "demo:Sheet1",
            "row_index": "1",
            "type": "excel",
            rag_module.VEC_FIELD: b"",
        },
    )

    monkeypatch.setattr(
        "app.core.rag.embed_texts",
        lambda texts: np.zeros((len(texts), 384), dtype=np.float32),
    )
    monkeypatch.setattr("app.core.rag._ensure_index", lambda *args, **kwargs: None)

    list_resp = client.get("/rag/context", params={"source": "demo:Sheet1"})
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json()["count"] >= 1

    update_resp = client.put(
        f"/rag/context/{doc_id}",
        json={"text": "Updated context text"},
    )
    assert update_resp.status_code == 200, update_resp.text
    stored = fake_redis.hgetall(key)
    assert stored["text"] == "Updated context text"

    note_resp = client.post(
        "/rag/context/note",
        json={"source": "demo:Sheet1", "text": "Vendor IDs map to cb_id."},
    )
    assert note_resp.status_code == 200, note_resp.text
    created = note_resp.json()["created"]
    assert created["type"] == "note"
    assert created["text"]
    assert created["source"] == "demo:Sheet1"

    final_resp = client.get("/rag/context", params={"source": "demo:Sheet1"})
    assert final_resp.status_code == 200, final_resp.text
    final_payload = final_resp.json()
    final_notes = final_payload.get("notes") or final_payload.get("chunks") or []
    assert final_payload["count"] >= 2
    assert any(c["type"] == "note" and c["text"] for c in final_notes)


def test_memory_endpoints(client, monkeypatch):
    from app.core.db import session_scope
    from app.core.models import Upload

    content = _xlsx_bytes()
    files = {
        "file": (
            "test.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    monkeypatch.setattr("app.core.rag._ensure_index", lambda *args, **kwargs: None)

    resp = client.post("/rag/index_excel", files=files)
    assert resp.status_code == 200
    payload = resp.json()
    sha = payload["sha16"]

    mem_resp = client.get("/rag/memory", params={"sha16": sha, "sheet": "Sheet1"})
    assert mem_resp.status_code == 200, mem_resp.text
    memory = mem_resp.json()
    assert memory["relationships"]
    assert isinstance(memory["analysis_plan"], list)

    new_relationships = {"Assigned_To": "resolver", "Category": "category"}
    update_resp = client.put(
        "/rag/memory",
        json={"sha16": sha, "sheet": "Sheet1", "relationships": new_relationships},
    )
    assert update_resp.status_code == 200, update_resp.text

    with session_scope() as s:
        rec = (
            s.execute(
                select(Upload)
                .where(Upload.sha16 == sha, Upload.sheet == "Sheet1")
                .order_by(Upload.uploaded_at.desc())
            )
            .scalars()
            .first()
        )
        assert rec is not None
        assert rec.summary.get("relationships") == new_relationships


def test_chat_uses_summary_metrics(client, monkeypatch):
    monkeypatch.setattr("app.core.rag._ensure_index", lambda *args, **kwargs: None)

    files = {
        "file": (
            "resolver.xlsx",
            _resolver_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    index_resp = client.post("/rag/index_excel", files=files)
    assert index_resp.status_code == 200, index_resp.text

    monkeypatch.setattr(
        "app.api.rag.search",
        lambda *_args, **_kwargs: [
            {
                "key": "resolver:summary",
                "source": "resolver.xlsx:Sheet1:summary",
                "text": "Summary chunk",
                "row_index": -1,
                "score": 0.1,
            }
        ],
    )

    chat_payload = {
        "messages": [
            {"role": "user", "content": "Who resolved the most tickets?"},
        ]
    }
    chat_resp = client.post("/rag/chat", json=chat_payload)
    assert chat_resp.status_code == 200, chat_resp.text
    assert "Alex" in chat_resp.json()["answer"]

    chat_payload_fast = {
        "messages": [
            {"role": "user", "content": "Who resolves tickets the fastest?"},
        ]
    }
    chat_resp_fast = client.post("/rag/chat", json=chat_payload_fast)
    assert chat_resp_fast.status_code == 200, chat_resp_fast.text
    assert "Priya" in chat_resp_fast.json()["answer"]
