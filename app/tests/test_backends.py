from __future__ import annotations

from fastapi.testclient import TestClient


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
    conn_id = connection["id"]

    list_resp = client.get("/backends")
    assert list_resp.status_code == 200
    connections = list_resp.json()["connections"]
    assert len(connections) == 1

    update_resp = client.put(
        f"/backends/{conn_id}",
        json={"config": {"bucket": "analytics", "region": "us-west-2"}},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["config"] == {"bucket": "analytics", "region": "us-west-2"}

    delete_resp = client.delete(f"/backends/{conn_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True

    final_list = client.get("/backends")
    assert final_list.status_code == 200
    assert final_list.json()["connections"] == []
