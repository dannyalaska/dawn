from __future__ import annotations

from fastapi.testclient import TestClient


def _ingest_sample_feed(client: TestClient) -> None:
    from io import BytesIO

    import pandas as pd

    df = pd.DataFrame(
        {
            "ticket_id": [1, 2, 2],
            "status": [" open", "closed ", "closed "],
            "agent_id": [10, 20, 20],
        }
    )
    buf = BytesIO()
    df.to_csv(buf, index=False)
    data = {
        "identifier": "tickets",
        "name": "Tickets",
        "source_type": "upload",
        "data_format": "csv",
    }
    files = {"file": ("tickets.csv", buf.getvalue(), "text/csv")}
    resp = client.post("/feeds/ingest", data=data, files=files)
    assert resp.status_code == 200, resp.text


def test_transform_dry_run_and_create_version():
    from app.api.server import app
    from app.core.db import session_scope
    from app.core.models import Transform, TransformVersion

    client = TestClient(app)
    _ingest_sample_feed(client)

    definition = {
        "name": "tickets_clean",
        "feed_identifier": "tickets",
        "target_table": "clean_tickets",
        "description": "Normalize ticket statuses",
        "steps": [
            {"type": "rename", "column": "ticket_id", "new_name": "id"},
            {"type": "trim", "column": "status", "method": "both"},
            {
                "type": "map_values",
                "column": "status",
                "mapping": {"open": "OPEN", "closed": "CLOSED"},
                "default": "UNKNOWN",
            },
            {"type": "deduplicate", "subset": ["id"], "keep": "first"},
        ],
        "load_strategy": "append",
        "generate_dbt_model": True,
        "unique_key": ["id"],
    }

    sample_rows = [
        {"ticket_id": 1, "status": " open", "agent_id": 10},
        {"ticket_id": 2, "status": "closed ", "agent_id": 20},
        {"ticket_id": 2, "status": "closed ", "agent_id": 20},
    ]

    dry_run = client.post(
        "/transforms/dry_run",
        json={
            "definition": definition,
            "sample_rows": sample_rows,
        },
    )
    assert dry_run.status_code == 200, dry_run.text
    diff = dry_run.json()["diff"]
    assert diff["rows_before"] == 3
    assert diff["rows_after"] == 2
    assert "id" in diff["preview_after"][0]

    create_resp = client.post(
        "/transforms",
        json={
            "definition": definition,
            "sample_rows": sample_rows,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    body = create_resp.json()
    assert body["version"] == 1
    assert "run_transform" in body["code"]
    assert body["dbt_model"] is not None
    assert body["dry_run"]["rows_after"] == 2
    assert "docs" in body
    assert "markdown" in body["docs"]

    with session_scope() as s:
        transform = s.query(Transform).filter(Transform.name == "tickets_clean").one()
        version = (
            s.query(TransformVersion).filter(TransformVersion.transform_id == transform.id).one()
        )
        assert version.version == 1
        assert version.dry_run_report["rows_after"] == 2
        assert "df = df.rename" in version.script
