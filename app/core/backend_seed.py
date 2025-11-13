from __future__ import annotations

import json
import os
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.engine.url import make_url

from app.core.backend_connectors import SUPPORTED_SCHEMA_BACKENDS
from app.core.db import session_scope
from app.core.models import BackendConnection


def _postgres_connection_from_env() -> dict[str, Any] | None:
    dsn = os.getenv("BACKEND_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
    if not dsn:
        return None
    try:
        url = make_url(dsn)
    except Exception:
        return None
    if not str(url.drivername or "").startswith("postgres"):
        return None
    name = os.getenv("BACKEND_POSTGRES_NAME", "Primary Postgres").strip() or "Primary Postgres"
    schema_env = os.getenv("BACKEND_POSTGRES_SCHEMA_GRANTS", "")
    schema_grants = [item.strip() for item in schema_env.split(",") if item.strip()]
    config: dict[str, Any] = {
        "host": url.host or "localhost",
        "port": int(url.port or 5432),
        "database": url.database or "",
        "user": url.username or "",
        "password": url.password or "",
    }
    for key, value in dict(url.query).items():
        config[str(key)] = value
    if schema_grants:
        config["schema_grants"] = schema_grants
    return {"name": name, "kind": "postgres", "config": config}


def _json_connections_from_env() -> list[dict[str, Any]]:
    raw = os.getenv("BACKEND_AUTO_CONNECTIONS")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    connections: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        kind = str(entry.get("kind", "")).strip().lower()
        config = entry.get("config")
        if not name or not kind or not isinstance(config, dict):
            continue
        config_dict = cast(dict[str, Any], dict(config))
        payload = {
            "name": name,
            "kind": kind,
            "config": config_dict,
        }
        schema_grants = entry.get("schema_grants")
        if isinstance(schema_grants, list):
            cleaned = [str(item).strip() for item in schema_grants if str(item).strip()]
            if cleaned:
                config_dict["schema_grants"] = cleaned
        connections.append(payload)
    return connections


def _gather_env_connections() -> list[dict[str, Any]]:
    connections = _json_connections_from_env()
    pg_entry = _postgres_connection_from_env()
    if pg_entry:
        connections.insert(0, pg_entry)
    return connections


def seed_backend_connections(user_id: int) -> None:
    connections = _gather_env_connections()
    if not connections:
        return
    with session_scope() as session:
        existing = {
            connection.name: connection
            for connection in session.execute(
                select(BackendConnection).where(BackendConnection.user_id == user_id)
            ).scalars()
        }
        for entry in connections:
            name = entry["name"]
            kind = entry["kind"]
            if kind not in SUPPORTED_SCHEMA_BACKENDS:
                continue
            if name in existing:
                continue
            config = dict(entry["config"])
            schema_grants = config.pop("schema_grants", None)
            if schema_grants:
                config["schema_grants"] = schema_grants
            connection = BackendConnection(
                user_id=user_id,
                name=name,
                kind=kind,
                config=config,
            )
            session.add(connection)
        session.flush()
