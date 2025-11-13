from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.auth import CurrentUser
from app.core.backend_connectors import (
    SUPPORTED_SCHEMA_BACKENDS,
    BackendConnectorError,
    get_schema_grants,
    list_backend_schemas,
    normalize_schema_list,
)
from app.core.db import session_scope
from app.core.models import BackendConnection

router = APIRouter(prefix="/backends", tags=["backends"])


class BackendCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    kind: Literal["postgres", "mysql", "s3", "snowflake"]
    config: dict[str, Any] = Field(default_factory=dict)
    schema_grants: list[str] | None = Field(
        default=None,
        description="Optional list of schemas the agent is allowed to query.",
    )


class BackendUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    config: dict[str, Any] | None = None
    schema_grants: list[str] | None = None


class SchemaGrantUpdateRequest(BaseModel):
    schemas: list[str] = Field(min_length=1)


def _serialize(connection: BackendConnection) -> dict[str, Any]:
    clean_config = dict(connection.config or {})
    clean_config.pop("schema_grants", None)
    payload = {
        "id": connection.id,
        "name": connection.name,
        "kind": connection.kind,
        "config": clean_config,
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
    }
    payload["schema_grants"] = get_schema_grants(connection.config)
    return payload


def _prepare_updated_config(
    original: dict[str, Any] | None,
    schema_grants: list[str] | None,
    *,
    fallback_grants: list[str] | None = None,
) -> dict[str, Any]:
    config = dict(original or {})
    if schema_grants is not None:
        config["schema_grants"] = normalize_schema_list(schema_grants)
    elif fallback_grants is not None:
        config["schema_grants"] = normalize_schema_list(fallback_grants)
    elif "schema_grants" not in config:
        config.setdefault("schema_grants", [])
    return config


@router.get("")
def list_connections(current_user: CurrentUser) -> dict[str, Any]:
    with session_scope() as session:
        rows = (
            session.execute(
                select(BackendConnection).where(BackendConnection.user_id == current_user.id)
            )
            .scalars()
            .all()
        )
        return {"connections": [_serialize(row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_connection(payload: BackendCreateRequest, current_user: CurrentUser) -> dict[str, Any]:
    if payload.schema_grants and payload.kind not in SUPPORTED_SCHEMA_BACKENDS:
        msg = "Schema grants are only supported for Postgres or Snowflake connections."
        raise HTTPException(status_code=400, detail=msg)

    with session_scope() as session:
        connection = BackendConnection(
            user_id=current_user.id,
            name=payload.name.strip(),
            kind=payload.kind,
            config=_prepare_updated_config(payload.config, payload.schema_grants),
        )
        session.add(connection)
        session.flush()
        session.refresh(connection)
        return _serialize(connection)


def _load_connection(session, connection_id: int, user_id: int) -> BackendConnection:
    connection = session.get(BackendConnection, connection_id)
    if connection is None or connection.user_id != user_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection


@router.put("/{connection_id}")
def update_connection(
    connection_id: int,
    payload: BackendUpdateRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    with session_scope() as session:
        connection = _load_connection(session, connection_id, current_user.id)
        if payload.schema_grants is not None and connection.kind not in SUPPORTED_SCHEMA_BACKENDS:
            msg = "Schema grants are only supported for Postgres or Snowflake connections."
            raise HTTPException(status_code=400, detail=msg)
        if payload.name:
            connection.name = payload.name.strip()
        if payload.config is not None:
            existing = get_schema_grants(connection.config)
            connection.config = _prepare_updated_config(
                payload.config,
                payload.schema_grants,
                fallback_grants=existing,
            )
        elif payload.schema_grants is not None:
            connection.config = _prepare_updated_config(connection.config, payload.schema_grants)
        session.flush()
        session.refresh(connection)
        return _serialize(connection)


@router.delete("/{connection_id}")
def delete_connection(connection_id: int, current_user: CurrentUser) -> dict[str, bool]:
    with session_scope() as session:
        connection = _load_connection(session, connection_id, current_user.id)
        session.delete(connection)
        session.flush()
    return {"ok": True}


@router.get("/{connection_id}/schemas")
def backend_schemas(connection_id: int, current_user: CurrentUser) -> dict[str, Any]:
    schemas: list[str]
    grants: list[str]
    with session_scope() as session:
        connection = _load_connection(session, connection_id, current_user.id)
        config = dict(connection.config or {})
        try:
            schemas = list_backend_schemas(connection.kind, config)
        except BackendConnectorError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        grants = get_schema_grants(config)
    return {"schemas": schemas, "grants": grants}


@router.post("/{connection_id}/schemas/grant")
def update_schema_grants(
    connection_id: int,
    payload: SchemaGrantUpdateRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    with session_scope() as session:
        connection = _load_connection(session, connection_id, current_user.id)
        if connection.kind not in SUPPORTED_SCHEMA_BACKENDS:
            msg = "Schema grants are only supported for Postgres or Snowflake connections."
            raise HTTPException(status_code=400, detail=msg)
        grants = normalize_schema_list(payload.schemas)
        connection.config = _prepare_updated_config(connection.config, grants)
        session.flush()
        session.refresh(connection)
        return {
            "connection": _serialize(connection),
            "schema_grants": connection.config.get("schema_grants", []),
        }
