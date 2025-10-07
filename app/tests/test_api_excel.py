from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient


def _xlsx_bytes() -> bytes:
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    return buf.getvalue()


def test_preview_recent_cached_flow():
    from app.api.server import app

    client = TestClient(app)

    # 1) /ingest/preview
    content = _xlsx_bytes()
    files = {
        "file": (
            "test.xlsx",
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    r = client.post("/ingest/preview", files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sheet"] == "Sheet1"
    assert data["shape"] == [3, 2]
    assert "sha16" in data
    sha16 = data["sha16"]

    # 2) /ingest/recent
    r2 = client.get("/ingest/recent?limit=5")
    assert r2.status_code == 200, r2.text
    rec = r2.json()
    assert any(row["sha16"] == sha16 for row in rec)

    # 3) /ingest/preview_cached
    r3 = client.get("/ingest/preview_cached", params={"sha16": sha16, "sheet": "Sheet1"})
    assert r3.status_code == 200, r3.text
    cached = r3.json()
    assert cached["name"] == "Sheet1"
    assert tuple(cached["shape"]) == (3, 2)
