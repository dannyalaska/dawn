from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi import File as UploadFileParam
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.auth import CurrentUser
from app.core.db import session_scope
from app.core.feed_ingest import FeedIngestConflict, FeedIngestError, ingest_feed
from app.core.limits import SizeLimitError, read_upload_bytes
from app.core.models import Feed, FeedVersion

router = APIRouter(prefix="/feeds", tags=["feeds"])

# Evaluate File(...) at import time to satisfy lint rule B008.
upload_file_param = UploadFileParam(default=None)


@router.post("/ingest")
async def feed_ingest(
    identifier: str = Form(..., min_length=3),
    name: str = Form(..., min_length=1),
    source_type: str = Form(default="upload"),
    data_format: str | None = Form(default=None),
    owner: str | None = Form(default=None),
    sheet: str | None = Form(default=None),
    s3_path: str | None = Form(default=None),
    http_url: str | None = Form(default=None),
    confirm_update: bool = Form(default=False),
    file: UploadFile | None = upload_file_param,
    *,
    current_user: CurrentUser,
) -> dict[str, Any]:
    try:
        file_bytes = (
            await read_upload_bytes(file, label="Feed upload") if file is not None else None
        )
    except SizeLimitError as exc:
        raise HTTPException(413, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Failed to read uploaded file: {exc}") from exc

    try:
        result = await run_in_threadpool(
            ingest_feed,
            identifier=identifier.strip(),
            name=name.strip(),
            source_kind=source_type,
            data_format=data_format,
            owner=owner.strip() if owner else None,
            file_bytes=file_bytes,
            filename=file.filename if file else None,
            sheet=sheet,
            s3_path=s3_path,
            http_url=http_url,
            user_id=current_user.id,
            confirm_update=confirm_update,
        )
    except FeedIngestConflict as exc:
        raise HTTPException(409, exc.payload) from exc
    except FeedIngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, "Feed ingestion failed") from exc

    return result


def _serialize_feed(feed: Feed, latest: FeedVersion | None) -> dict[str, Any]:
    source_cfg = dict(feed.source_config or {})
    favorite_sheet = source_cfg.get("favorite_sheet") or source_cfg.get("sheet")

    latest_payload: dict[str, Any] | None = None
    if latest is not None:
        summary = dict(latest.summary_json or {})
        profile = dict(latest.profile or {})
        schema = dict(latest.schema_ or {})
        manifest = summary.get("manifest")
        sheet_names = summary.get("sheet_names") or profile.get("sheet_names") or []
        sheet = summary.get("sheet") or schema.get("sheet") or source_cfg.get("sheet")
        latest_payload = {
            "id": latest.id,
            "number": latest.version,
            "rows": latest.row_count,
            "columns": latest.column_count,
            "sha16": latest.sha16,
            "created_at": latest.created_at.isoformat() if latest.created_at else None,
            "sheet": sheet,
            "sheet_names": sheet_names,
            "summary": summary,
            "profile": profile,
            "schema": schema,
            "manifest": manifest,
        }

    return {
        "identifier": feed.identifier,
        "name": feed.name,
        "owner": feed.owner,
        "source_type": feed.source_type,
        "format": source_cfg.get("format"),
        "created_at": feed.created_at.isoformat() if feed.created_at else None,
        "updated_at": feed.updated_at.isoformat() if feed.updated_at else None,
        "favorite_sheet": favorite_sheet,
        "latest_version": latest_payload,
    }


@router.get("")
def feeds_index(current_user: CurrentUser) -> dict[str, Any]:
    feeds: list[dict[str, Any]] = []
    with session_scope() as session:
        feed_rows = (
            session.execute(
                select(Feed).where(Feed.user_id == current_user.id).order_by(Feed.created_at.asc())
            )
            .scalars()
            .all()
        )
        for feed in feed_rows:
            latest = (
                session.execute(
                    select(FeedVersion)
                    .where(FeedVersion.feed_id == feed.id, FeedVersion.user_id == current_user.id)
                    .order_by(FeedVersion.version.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            feeds.append(_serialize_feed(feed, latest))
    return {"feeds": feeds}


@router.get("/{identifier}")
def feed_detail(identifier: str, current_user: CurrentUser) -> dict[str, Any]:
    with session_scope() as session:
        feed = (
            session.execute(
                select(Feed).where(
                    Feed.identifier == identifier.strip(), Feed.user_id == current_user.id
                )
            )
            .scalars()
            .first()
        )
        if feed is None:
            raise HTTPException(404, f"Feed {identifier!r} not found")
        versions = (
            session.execute(
                select(FeedVersion)
                .where(FeedVersion.feed_id == feed.id, FeedVersion.user_id == current_user.id)
                .order_by(FeedVersion.version.desc())
            )
            .scalars()
            .all()
        )

        latest = versions[0] if versions else None
        payload = _serialize_feed(feed, latest)
        payload["versions"] = [
            {
                "id": version.id,
                "number": version.version,
                "rows": version.row_count,
                "columns": version.column_count,
                "sha16": version.sha16,
                "created_at": version.created_at.isoformat() if version.created_at else None,
                "summary": dict(version.summary_json or {}),
                "profile": dict(version.profile or {}),
                "schema": dict(version.schema_ or {}),
            }
            for version in versions
        ]
    return payload


class FavoriteRequest(BaseModel):
    sheet: str = Field(min_length=1)


@router.post("/{identifier}/favorite")
def feed_favorite(
    identifier: str,
    payload: FavoriteRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    sheet = payload.sheet.strip()
    if not sheet:
        raise HTTPException(400, "Sheet name is required")

    with session_scope() as session:
        feed = (
            session.execute(
                select(Feed).where(
                    Feed.identifier == identifier.strip(), Feed.user_id == current_user.id
                )
            )
            .scalars()
            .first()
        )
        if feed is None:
            raise HTTPException(404, f"Feed {identifier!r} not found")

        cfg = dict(feed.source_config or {})
        cfg["favorite_sheet"] = sheet
        feed.source_config = cfg
        session.flush()

        latest = (
            session.execute(
                select(FeedVersion)
                .where(FeedVersion.feed_id == feed.id, FeedVersion.user_id == current_user.id)
                .order_by(FeedVersion.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        result = _serialize_feed(feed, latest)
    return result
