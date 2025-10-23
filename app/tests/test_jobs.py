from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.auth import ensure_default_user


def _ingest_feed(client: TestClient) -> None:
    df = pd.DataFrame(
        {
            "ticket_id": [1, 2, 2],
            "status": [" open", "closed ", "closed "],
            "agent_id": [10, 20, 20],
        }
    )
    buf = BytesIO()
    df.to_csv(buf, index=False)
    resp = client.post(
        "/feeds/ingest",
        data={
            "identifier": "tickets",
            "name": "Tickets",
            "source_type": "upload",
            "data_format": "csv",
        },
        files={"file": ("tickets.csv", buf.getvalue(), "text/csv")},
    )
    assert resp.status_code == 200, resp.text


def _create_transform(client: TestClient) -> None:
    definition = {
        "name": "tickets_clean",
        "feed_identifier": "tickets",
        "target_table": "clean_tickets",
        "description": "Normalize ticket statuses",
        "steps": [
            {"type": "rename", "column": "ticket_id", "new_name": "id"},
            {"type": "trim", "column": "status"},
            {
                "type": "map_values",
                "column": "status",
                "mapping": {"open": "OPEN", "closed": "CLOSED"},
                "default": "UNKNOWN",
            },
            {"type": "deduplicate", "subset": ["id"], "keep": "first"},
        ],
        "load_strategy": "append",
        "generate_dbt_model": False,
    }
    sample_rows = [
        {"ticket_id": 1, "status": " open", "agent_id": 10},
        {"ticket_id": 2, "status": "closed ", "agent_id": 20},
        {"ticket_id": 2, "status": "closed ", "agent_id": 20},
    ]
    resp = client.post(
        "/transforms",
        json={
            "definition": definition,
            "sample_rows": sample_rows,
        },
    )
    assert resp.status_code == 200, resp.text


def test_job_run_endpoint_creates_run_record():
    from app.api.server import app
    from app.core.db import session_scope
    from app.core.models import Job, JobRun

    client = TestClient(app)
    _ingest_feed(client)
    _create_transform(client)

    job_resp = client.post(
        "/jobs",
        json={
            "name": "tickets_job",
            "feed_identifier": "tickets",
            "transform_name": "tickets_clean",
        },
    )
    assert job_resp.status_code == 200, job_resp.text
    job_id = job_resp.json()["id"]

    run_resp = client.post(f"/jobs/{job_id}/run")
    assert run_resp.status_code == 200, run_resp.text
    payload = run_resp.json()
    assert payload["run"]["status"] == "success"
    assert payload["run"]["rows_out"] == 2

    user_ctx = ensure_default_user()
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        assert job.user_id == user_ctx.id
        runs = (
            session.execute(
                select(JobRun).where(JobRun.job_id == job.id, JobRun.user_id == user_ctx.id)
            )
            .scalars()
            .all()
        )
        assert len(runs) == 1
