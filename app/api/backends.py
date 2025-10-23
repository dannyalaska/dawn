from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.auth import CurrentUser
from app.core.db import session_scope
from app.core.models import BackendConnection

router = APIRouter(prefix="/backends", tags=["backends"])


class BackendCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    kind: Literal["postgres", "mysql", "s3"]
    config: dict[str, Any] = Field(default_factory=dict)


class BackendUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    config: dict[str, Any] | None = None


def _serialize(connection: BackendConnection) -> dict[str, Any]:
    return {
        "id": connection.id,
        "name": connection.name,
        "kind": connection.kind,
        "config": connection.config or {},
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
    }


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
    with session_scope() as session:
        connection = BackendConnection(
            user_id=current_user.id,
            name=payload.name.strip(),
            kind=payload.kind,
            config=payload.config,
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
        if payload.name:
            connection.name = payload.name.strip()
        if payload.config is not None:
            connection.config = payload.config
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
