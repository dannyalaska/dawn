from __future__ import annotations

from fastapi.testclient import TestClient


def _ingest_feed(client: TestClient) -> None:
    from io import BytesIO

    import pandas as pd

    df = pd.DataFrame(
        {
            "ticket_id": [1, 2, 3],
            "status": ["open", "closed", "open"],
            "owner": ["Alex", "Priya", "Alex"],
        }
    )
    buf = BytesIO()
    df.to_csv(buf, index=False)
    files = {"file": ("tickets.csv", buf.getvalue(), "text/csv")}
    data = {
        "identifier": "tickets",
        "name": "Tickets",
        "source_type": "upload",
        "data_format": "csv",
    }
    resp = client.post("/feeds/ingest", data=data, files=files)
    assert resp.status_code == 200, resp.text


def test_nl_sql_generates_select_and_records_history():
    from app.api.server import app

    client = TestClient(app)
    _ingest_feed(client)

    payload = {"question": "List all tickets", "explain": False}
    first = client.post("/nl/sql", json=payload)
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["validation"]["ok"] is True
    assert "SELECT" in data["sql"].upper()
    assert "tickets" in data["sql"].lower()
    assert data["citations"]["tables"]

    second = client.post("/nl/sql", json={"question": "Count tickets"})
    assert second.status_code == 200, second.text
    history = second.json()["recent_questions"]
    assert "List all tickets" in history
