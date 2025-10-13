from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi import File as UploadFileParam

from app.core.feed_ingest import FeedIngestError, ingest_feed

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
    file: UploadFile | None = upload_file_param,
) -> dict[str, Any]:
    try:
        file_bytes = await file.read() if file is not None else None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Failed to read uploaded file: {exc}") from exc

    try:
        result = ingest_feed(
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
        )
    except FeedIngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, "Feed ingestion failed") from exc

    return result
