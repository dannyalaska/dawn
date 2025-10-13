from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient


def _csv_bytes() -> bytes:
    df = pd.DataFrame(
        {
            "ticket_id": [101, 102, 103],
            "assigned_to": ["Alex", "Priya", "Alex"],
            "status": ["open", "closed", "open"],
        }
    )
    buf = BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def test_feed_ingest_upload_creates_version_and_summary():
    from app.api.server import app
    from app.core.db import session_scope
    from app.core.models import DQRule, Feed, FeedVersion
    from app.core.redis_client import redis_sync

    client = TestClient(app)

    content = _csv_bytes()
    data = {
        "identifier": "tickets",
        "name": "Tickets",
        "source_type": "upload",
        "data_format": "csv",
        "owner": "ops",
    }
    files = {"file": ("tickets.csv", content, "text/csv")}

    resp = client.post("/feeds/ingest", data=data, files=files)
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["feed"]["identifier"] == "tickets"
    assert payload["version"]["number"] == 1
    assert "ticket_id" in payload["schema"]["primary_keys"]
    assert "markdown" in payload["summary"]
    assert "Rows" in payload["summary"]["markdown"]
    assert "mermaid" in payload["summary"].get("json", {})
    assert "manifest" in payload
    assert payload["manifest"]["feed"]["identifier"] == "tickets"
    drift = payload.get("drift")
    assert drift is not None
    assert drift["status"] in {"baseline", "no_change", "changed"}

    # DB persisted
    with session_scope() as s:
        feed = s.query(Feed).filter(Feed.identifier == "tickets").one()
        assert feed.name == "Tickets"
        version = (
            s.query(FeedVersion)
            .filter(FeedVersion.feed_id == feed.id, FeedVersion.version == 1)
            .one()
        )
        assert version.row_count == 3
        assert version.column_count == 3
        assert version.summary_markdown
        dq_rules = (
            s.query(DQRule)
            .filter(DQRule.feed_version_id == version.id, DQRule.is_manual.is_(False))
            .all()
        )
        assert dq_rules
        assert any(rule.rule_type == "row_count_min" for rule in dq_rules)

    redis_key = "dawn:feed:tickets:v1"
    stored = redis_sync.hgetall(redis_key)
    assert stored
    assert "summary_markdown" in stored
    assert "tickets" in stored["summary_markdown"]
