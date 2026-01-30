from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text

from app.core.auth import CurrentUser
from app.core.config import settings
from app.core.db import get_engine, session_scope
from app.core.models import (
    BackendConnection,
    DQResult,
    DQRule,
    Feed,
    FeedDataset,
    FeedVersion,
    Job,
    JobRun,
    Transform,
    TransformVersion,
    Upload,
)
from app.core.nl2sql import RECENT_KEY
from app.core.redis_client import redis_sync

router = APIRouter(prefix="/admin", tags=["admin"])

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


class ResetRequest(BaseModel):
    confirm: bool = Field(default=False)


def _reset_allowed() -> bool:
    if settings.ALLOW_RESET:
        return True
    return settings.ENV.lower() in {"dev", "local", "test"}


def _safe_name(value: str | None) -> str | None:
    if not value:
        return None
    return value if _SAFE_NAME.match(value) else None


def _delete_redis_keys(pattern: str) -> int:
    keys = list(redis_sync.scan_iter(match=pattern))
    if keys:
        redis_sync.delete(*keys)
    return len(keys)


@router.post("/reset")
def reset_workspace(payload: ResetRequest, current_user: CurrentUser) -> dict[str, Any]:
    if not _reset_allowed():
        raise HTTPException(403, "Workspace reset is disabled in this environment.")
    if not payload.confirm:
        raise HTTPException(400, "confirm=true is required to reset the workspace.")

    user_id = current_user.id
    deleted: dict[str, int] = {}

    with session_scope() as session:
        feed_ids = session.execute(select(Feed.id).where(Feed.user_id == user_id)).scalars().all()
        feed_version_ids: list[int] = []
        if feed_ids:
            feed_version_ids = (
                session.execute(select(FeedVersion.id).where(FeedVersion.feed_id.in_(feed_ids)))
                .scalars()
                .all()
            )

        dq_rule_ids: list[int] = []
        if feed_version_ids:
            dq_rule_ids = (
                session.execute(
                    select(DQRule.id).where(DQRule.feed_version_id.in_(feed_version_ids))
                )
                .scalars()
                .all()
            )

        dataset_rows = []
        if feed_ids:
            dataset_rows = session.execute(
                select(FeedDataset.schema_name, FeedDataset.table_name).where(
                    FeedDataset.feed_id.in_(feed_ids)
                )
            ).all()

        if dq_rule_ids:
            deleted["dq_results"] = (
                session.execute(delete(DQResult).where(DQResult.rule_id.in_(dq_rule_ids))).rowcount
                or 0
            )
        else:
            deleted["dq_results"] = 0

        if feed_version_ids:
            deleted["dq_rules"] = (
                session.execute(
                    delete(DQRule).where(DQRule.feed_version_id.in_(feed_version_ids))
                ).rowcount
                or 0
            )
        else:
            deleted["dq_rules"] = 0

        deleted["job_runs"] = (
            session.execute(delete(JobRun).where(JobRun.user_id == user_id)).rowcount or 0
        )
        deleted["jobs"] = session.execute(delete(Job).where(Job.user_id == user_id)).rowcount or 0
        deleted["transform_versions"] = (
            session.execute(
                delete(TransformVersion).where(TransformVersion.user_id == user_id)
            ).rowcount
            or 0
        )
        deleted["transforms"] = (
            session.execute(delete(Transform).where(Transform.user_id == user_id)).rowcount or 0
        )
        if feed_version_ids:
            deleted["feed_datasets"] = (
                session.execute(
                    delete(FeedDataset).where(FeedDataset.feed_version_id.in_(feed_version_ids))
                ).rowcount
                or 0
            )
        else:
            deleted["feed_datasets"] = 0
        if feed_ids:
            deleted["feed_versions"] = (
                session.execute(
                    delete(FeedVersion).where(FeedVersion.feed_id.in_(feed_ids))
                ).rowcount
                or 0
            )
        else:
            deleted["feed_versions"] = 0
        deleted["feeds"] = (
            session.execute(delete(Feed).where(Feed.user_id == user_id)).rowcount or 0
        )
        deleted["uploads"] = (
            session.execute(delete(Upload).where(Upload.user_id == user_id)).rowcount or 0
        )
        deleted["backend_connections"] = (
            session.execute(
                delete(BackendConnection).where(BackendConnection.user_id == user_id)
            ).rowcount
            or 0
        )

    dropped_tables = 0
    if dataset_rows:
        engine = get_engine()
        with engine.begin() as conn:
            for schema_name, table_name in dataset_rows:
                safe_table = _safe_name(str(table_name))
                if not safe_table:
                    continue
                safe_schema = _safe_name(str(schema_name)) if schema_name else None
                if safe_schema:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{safe_schema}"."{safe_table}"'))
                else:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{safe_table}"'))
                dropped_tables += 1

    redis_deleted = {
        "rag_docs": _delete_redis_keys(f"dawn:rag:doc:{user_id}:*"),
        "rag_answers": _delete_redis_keys(f"dawn:ans:{user_id}:*"),
        "feed_summaries": _delete_redis_keys(f"dawn:user:{user_id}:feed:*"),
        "preview_cache": _delete_redis_keys(f"dawn:dev:preview:{user_id}:*"),
        "nl2sql_recent": _delete_redis_keys(f"{RECENT_KEY}:{user_id}"),
    }

    return {
        "ok": True,
        "deleted": deleted,
        "dropped_tables": dropped_tables,
        "redis_deleted": redis_deleted,
    }
