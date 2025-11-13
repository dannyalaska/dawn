from __future__ import annotations

from contextlib import suppress
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import select

from app.core import agent_graph
from app.core.db import get_engine, session_scope
from app.core.models import BackendConnection, Feed, FeedDataset, FeedVersion


@pytest.fixture(autouse=True)
def _reset_agent_graph_cache():
    with suppress(AttributeError):
        agent_graph._compiled_graph.cache_clear()  # type: ignore[attr-defined]
    yield
    with suppress(AttributeError):
        agent_graph._compiled_graph.cache_clear()  # type: ignore[attr-defined]


def _seed_feed(identifier: str, summary: dict[str, Any], user_id: int = 1) -> None:
    with session_scope() as session:
        feed = Feed(
            identifier=identifier,
            name=summary.get("feed_name", identifier.replace("_", " ").title()),
            source_type="upload",
            owner="test",
            user_id=user_id,
            source_config={"format": "excel"},
        )
        session.add(feed)
        session.flush()
        version = FeedVersion(
            feed_id=feed.id,
            version=1,
            upload_id=None,
            sha16="abc123def4567890",
            schema_={"columns": []},
            profile={"columns": []},
            summary_markdown="",
            summary_json=summary,
            row_count=summary.get("row_count", 0),
            column_count=summary.get("column_count", 0),
            user_id=user_id,
        )
        session.add(version)
        session.commit()


def _seed_materialized_dataset(identifier: str, columns: list[str]) -> None:
    engine = get_engine()
    table_name = f"dawn_feed_{identifier}_v1"
    df = pd.DataFrame([{col: f"{col}_value" for col in columns}])
    df.to_sql(table_name, con=engine, if_exists="replace", index=False)
    with session_scope() as session:
        feed = session.execute(select(Feed).where(Feed.identifier == identifier)).scalars().first()
        assert feed is not None
        version = (
            session.execute(select(FeedVersion).where(FeedVersion.feed_id == feed.id))
            .scalars()
            .first()
        )
        assert version is not None
        dataset = FeedDataset(
            feed_id=feed.id,
            feed_version_id=version.id,
            table_name=table_name,
            schema_name=getattr(engine.dialect, "default_schema_name", None),
            storage="database",
            columns=columns,
            row_count=len(df),
            column_count=len(columns),
        )
        session.add(dataset)
        session.commit()


def _seed_backend_connection(user_id: int = 1, *, schemas: list[str] | None = None) -> int:
    with session_scope() as session:
        connection = BackendConnection(
            user_id=user_id,
            name="Warehouse",
            kind="postgres",
            config={
                "schema_grants": schemas or ["analytics"],
                "host": "localhost",
                "port": 5432,
                "database": "warehouse",
                "user": "svc",
                "password": "secret",
            },
        )
        session.add(connection)
        session.commit()
        return connection.id


def test_multi_agent_session_handles_metrics(monkeypatch):
    summary = {
        "analysis_plan": [
            {"type": "count_by", "column": "Status"},
            {"type": "avg_by", "group": "Agent", "value": "Resolution_Time", "stat": "mean"},
        ],
        "insights": {
            "Status": [
                {"label": "Closed", "count": 5},
                {"label": "Open", "count": 2},
            ]
        },
        "aggregates": [
            {
                "group": "Agent",
                "value": "Resolution_Time",
                "stat": "mean",
                "best": [
                    {"label": "Alex", "value": 4.2},
                    {"label": "Priya", "value": 4.5},
                ],
                "worst": [
                    {"label": "Sam", "value": 8.8},
                ],
            }
        ],
        "columns": [
            {"name": "Status", "dtype": "string"},
            {"name": "Agent", "dtype": "string"},
            {"name": "Resolution_Time", "dtype": "float", "stats": {"mean": 5.5}},
        ],
        "relationships": {"Agent": "resolver"},
        "text": "Tickets summary with resolver performance.",
        "row_count": 7,
        "column_count": 3,
    }
    _seed_feed("support_tickets", summary)

    def fake_run_chat(messages, *, k: int, user_id: str):
        assert messages[-1]["role"] == "user"
        return {"answer": "Stub answer.", "sources": [{"id": "doc1"}]}

    monkeypatch.setattr(agent_graph, "run_chat", fake_run_chat)
    monkeypatch.setattr(agent_graph, "upsert_chunks", lambda chunks, user_id: len(chunks))

    state = agent_graph.run_multi_agent_session(
        feed_identifier="support_tickets",
        user_id="1",
        question="Who resolved the most tickets?",
    )

    assert len(state.get("plan", [])) == 2
    assert len(state.get("completed", [])) == 2
    assert state.get("answer") == "Stub answer."
    assert any(entry.get("agent") == "qa" for entry in state.get("run_log", []))
    assert state.get("context_updates")
    assert state.get("final_report")


def test_multi_agent_session_fallback_tools(monkeypatch):
    summary = {
        "analysis_plan": [
            {"type": "profile_column", "column": "Status"},
        ],
        "columns": [
            {
                "name": "Status",
                "dtype": "string",
                "top_values": [{"label": "Closed", "count": 10}],
            }
        ],
        "relationships": {"Status": "category"},
        "text": "Fallback summary text.",
    }
    _seed_feed("support_tickets_fallback", summary)

    def fake_run_chat(messages, *, k: int, user_id: str):
        return {"answer": "", "sources": []}

    monkeypatch.setattr(agent_graph, "run_chat", fake_run_chat)
    monkeypatch.setattr(agent_graph, "upsert_chunks", lambda chunks, user_id: len(chunks))

    state = agent_graph.run_multi_agent_session(
        feed_identifier="support_tickets_fallback",
        user_id="1",
    )

    assert state.get("completed")
    result = state["completed"][0]
    assert result["data"]["source"] in {"column_profile", "dataset_summary", "fallback"}
    assert state.get("warnings")


def test_agent_schema_inventory_from_feed_dataset(monkeypatch):
    summary = {
        "analysis_plan": [
            {"type": "count_by", "column": "Status"},
        ],
        "insights": {
            "Status": [
                {"label": "Closed", "count": 5},
            ]
        },
        "columns": [{"name": "Status", "dtype": "string"}],
    }
    _seed_feed("materialized_feed", summary)
    _seed_materialized_dataset("materialized_feed", ["Status", "Agent"])

    def fake_run_chat(messages, *, k: int, user_id: str):
        return {"answer": "", "sources": []}

    monkeypatch.setattr(agent_graph, "run_chat", fake_run_chat)
    monkeypatch.setattr(agent_graph, "upsert_chunks", lambda chunks, user_id: len(chunks))

    state = agent_graph.run_multi_agent_session(
        feed_identifier="materialized_feed",
        user_id="1",
        max_plan_steps=5,
    )

    assert any(task["type"] == "schema_inventory" for task in state.get("plan", []))
    assert any(result["type"] == "schema_inventory" for result in state.get("completed", []))


def test_multi_agent_includes_schema_inventory(monkeypatch):
    summary = {
        "analysis_plan": [
            {"type": "count_by", "column": "Status"},
        ],
        "insights": {
            "Status": [
                {"label": "Closed", "count": 5},
            ]
        },
        "columns": [{"name": "Status", "dtype": "string"}],
    }
    _seed_feed("support_schema", summary)
    _seed_backend_connection()

    def fake_run_chat(messages, *, k: int, user_id: str):
        return {"answer": "", "sources": []}

    monkeypatch.setattr(agent_graph, "run_chat", fake_run_chat)
    monkeypatch.setattr(agent_graph, "upsert_chunks", lambda chunks, user_id: len(chunks))
    monkeypatch.setattr(
        agent_graph,
        "list_backend_tables",
        lambda kind, config, schemas: [
            {"schema": "analytics", "table": "tickets", "columns": ["id", "status", "agent"]},
            {"schema": "analytics", "table": "agents", "columns": ["name", "team"]},
        ],
    )

    state = agent_graph.run_multi_agent_session(
        feed_identifier="support_schema",
        user_id="1",
        max_plan_steps=5,
    )

    assert any(task["type"] == "schema_inventory" for task in state.get("plan", []))
    assert any(result["type"] == "schema_inventory" for result in state.get("completed", []))
