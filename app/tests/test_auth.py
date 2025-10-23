from __future__ import annotations

from fastapi.testclient import TestClient


def test_register_login_and_me(monkeypatch):
    from app.api.server import app

    client = TestClient(app)

    resp = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "supersecret", "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    token = payload["token"]
    assert payload["user"]["email"] == "user@example.com"

    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_payload = me_resp.json()
    assert me_payload["email"] == "user@example.com"
    assert not me_payload["is_default"]

    login_resp = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "supersecret"}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["user"]["email"] == "user@example.com"

    duplicate = client.post(
        "/auth/register", json={"email": "user@example.com", "password": "anotherpw"}
    )
    assert duplicate.status_code == 400
