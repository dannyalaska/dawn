from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.server import app
from app.core.db import get_engine, session_scope
from app.core.models import FeedDataset


def test_feed_ingest_materializes_dataset():
    client = TestClient(app)
    csv_bytes = b"Agent,Status\nAlex,Closed\nPriya,Open\n"
    resp = client.post(
        "/feeds/ingest",
        data={
            "identifier": "materialized_feed",
            "name": "Materialized Feed",
            "source_type": "upload",
            "data_format": "csv",
        },
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    payload = resp.json()
    materialized = payload.get("materialized_table")
    assert materialized
    table_name = materialized["table"]

    with session_scope() as session:
        dataset = session.query(FeedDataset).filter(FeedDataset.table_name == table_name).one()
        assert dataset.row_count == 2
        assert dataset.column_count == 2

    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        assert count == 2
