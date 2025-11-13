from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select


def test_backend_connections_crud():
    from app.api.server import app

    client = TestClient(app)

    # Initially empty
    resp = client.get("/backends")
    assert resp.status_code == 200
    assert resp.json()["connections"] == []

    create_resp = client.post(
        "/backends",
        json={
            "name": "Local Postgres",
            "kind": "postgres",
            "config": {"dsn": "postgresql://user:pass@localhost/db"},
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    connection = create_resp.json()
    assert connection["name"] == "Local Postgres"
    assert connection["schema_grants"] == []
    conn_id = connection["id"]

    list_resp = client.get("/backends")
    assert list_resp.status_code == 200
    connections = list_resp.json()["connections"]
    assert len(connections) == 1

    update_resp = client.put(
        f"/backends/{conn_id}",
        json={
            "config": {"bucket": "analytics", "region": "us-west-2"},
            "schema_grants": ["public"],
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["config"] == {"bucket": "analytics", "region": "us-west-2"}
    assert update_resp.json()["schema_grants"] == ["public"]

    delete_resp = client.delete(f"/backends/{conn_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True

    final_list = client.get("/backends")
    assert final_list.status_code == 200
    assert final_list.json()["connections"] == []


def test_backend_schema_listing_and_grants(monkeypatch):
    from app.api.server import app

    client = TestClient(app)

    create_resp = client.post(
        "/backends",
        json={
            "name": "Analytics Warehouse",
            "kind": "postgres",
            "config": {
                "host": "localhost",
                "port": 5432,
                "database": "warehouse",
                "user": "svc",
                "password": "secret",
            },
        },
    )
    assert create_resp.status_code == 201
    conn_id = create_resp.json()["id"]

    captured: dict[str, Any] = {}

    def fake_list(kind: str, config: dict[str, Any]) -> list[str]:
        captured["kind"] = kind
        captured["config"] = config
        return ["finance", "public"]

    monkeypatch.setattr("app.api.backends.list_backend_schemas", fake_list)

    list_resp = client.get(f"/backends/{conn_id}/schemas")
    assert list_resp.status_code == 200
    assert list_resp.json()["schemas"] == ["finance", "public"]
    assert captured["kind"] == "postgres"

    grant_resp = client.post(
        f"/backends/{conn_id}/schemas/grant",
        json={"schemas": ["finance", "sales"]},
    )
    assert grant_resp.status_code == 200
    payload = grant_resp.json()
    assert payload["schema_grants"] == ["finance", "sales"]
    assert payload["connection"]["schema_grants"] == ["finance", "sales"]

    # Unsupported backend should fail when granting schemas
    s3_resp = client.post(
        "/backends",
        json={
            "name": "Assets",
            "kind": "s3",
            "config": {"bucket": "assets"},
        },
    )
    s3_id = s3_resp.json()["id"]
    deny_resp = client.post(
        f"/backends/{s3_id}/schemas/grant",
        json={"schemas": ["ignored"]},
    )
    assert deny_resp.status_code == 400


def test_seed_backend_connections(monkeypatch):
    from app.core.auth import ensure_default_user
    from app.core.backend_seed import seed_backend_connections
    from app.core.db import session_scope
    from app.core.models import BackendConnection

    monkeypatch.setenv("POSTGRES_DSN", "postgresql://demo:pass@localhost:5432/demo")
    monkeypatch.setenv("BACKEND_POSTGRES_NAME", "Demo Warehouse")
    monkeypatch.setenv("BACKEND_POSTGRES_SCHEMA_GRANTS", "analytics,public")

    user = ensure_default_user()
    seed_backend_connections(user.id)
    with session_scope() as session:
        entries = (
            session.execute(select(BackendConnection).where(BackendConnection.user_id == user.id))
            .scalars()
            .all()
        )
        names = [conn.name for conn in entries]
        configs = {conn.name: conn.config for conn in entries}
    assert "Demo Warehouse" in names
    assert configs["Demo Warehouse"].get("schema_grants") == ["analytics", "public"]
