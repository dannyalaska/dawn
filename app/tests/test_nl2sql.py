from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from app.core import nl2sql
from app.core.db import get_engine, session_scope
from app.core.models import BackendConnection, Feed, FeedDataset, FeedVersion


def _seed_backend_connection(user_id: int = 1):
    with session_scope() as session:
        connection = BackendConnection(
            user_id=user_id,
            name="Warehouse",
            kind="postgres",
            config={
                "schema_grants": ["analytics"],
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


def _seed_feed_version(identifier: str = "dataset_feed", user_id: int = 1) -> None:
    with session_scope() as session:
        feed = Feed(
            identifier=identifier,
            name="Dataset Feed",
            source_type="upload",
            owner="test",
            user_id=user_id,
            source_config={"format": "csv"},
        )
        session.add(feed)
        session.flush()
        session.add(
            FeedVersion(
                feed_id=feed.id,
                version=1,
                upload_id=None,
                sha16="datasetsha",
                schema_={"columns": []},
                profile={"columns": []},
                summary_json={"columns": []},
                row_count=0,
                column_count=0,
                user_id=user_id,
            )
        )
        session.commit()


def _seed_feed_dataset(identifier: str = "dataset_feed") -> str:
    engine = get_engine()
    table_name = f"dawn_feed_{identifier}_v1"
    df = pd.DataFrame([{"Status": "Closed", "Agent": "Alex"}])
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
            columns=["Status", "Agent"],
            row_count=1,
            column_count=2,
        )
        session.add(dataset)
        session.commit()
    return table_name


def test_build_manifest_includes_backend_tables(monkeypatch):
    _seed_backend_connection()

    monkeypatch.setattr(
        nl2sql,
        "list_backend_tables",
        lambda kind, config, schemas: [
            {"schema": "analytics", "table": "tickets", "columns": ["id", "status"]}
        ],
    )

    manifest = nl2sql.build_manifest(user_id=1)
    assert any(entry.name == "analytics.tickets" for entry in manifest)


def test_validate_sql_accepts_schema_tables():
    table = nl2sql.TableManifest(
        name="analytics.tickets",
        columns=["id", "status"],
        source="backend:1:analytics.tickets",
        primary_keys=[],
        foreign_keys=[],
        description="Warehouse",
        kind="postgres",
        schema="analytics",
        table="tickets",
        connection_id=1,
    )
    result = nl2sql.validate_sql("SELECT id FROM analytics.tickets", [table])
    assert result["ok"] is True
    assert "analytics.tickets" in result["tables"]


def test_build_manifest_includes_feed_dataset():
    identifier = "dataset_feed"
    _seed_feed_version(identifier)
    table_name = _seed_feed_dataset(identifier)
    manifest = nl2sql.build_manifest(user_id=1)
    assert any(entry.name == table_name for entry in manifest)
