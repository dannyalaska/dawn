from __future__ import annotations

from hashlib import sha256
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from sqlalchemy import delete, desc, select

from app.core.db import session_scope
from app.core.excel.ingestion import preview_from_bytes
from app.core.models import Upload
from app.core.redis_client import redis_sync

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Avoid B008: evaluate File(...) at import time, not in the signature default
file_param = File(...)


@router.post("/preview")
async def preview(sheet: str | None = Query(default=None), file: UploadFile = file_param):
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(400, "Only Excel files are supported (.xlsx, .xlsm, .xls)")
    content = await file.read()
    try:
        table = preview_from_bytes(content, sheet_name=sheet)
    except Exception as e:
        # keep original error chained for logs/tracebacks
        raise HTTPException(400, f"Failed to read Excel: {e}") from e

    digest = sha256(content).hexdigest()[:16]
    size_bytes = len(content)
    rows, cols = table.shape

    # Best-effort persistence; don't block preview on DB failure
    try:
        with session_scope() as s:
            s.add(
                Upload(
                    filename=(file.filename or "unknown"),
                    sheet=table.name,
                    sha16=digest,
                    size_bytes=size_bytes,
                    rows=rows,
                    cols=cols,
                )
            )
    except Exception as err:
        # TODO: switch to structured logging later
        print(f"[uploads] persist failed: {err}")

    return {
        "sheet": table.name,
        "shape": table.shape,
        "columns": table.columns,
        "rows": table.rows,
        "cached": table.cached,
        "sha16": digest,
        "sheet_names": table.sheet_names or [],
    }


def _preview_cache_key(sha16: str, sheet: str | None) -> str:
    # Must match app.core.excel.ingestion.cache_key
    suffix = f":{sheet}" if sheet else ""
    return f"dawn:dev:preview:{sha16}{suffix}"


@router.get("/recent")
def recent_uploads(limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    with session_scope() as s:
        rows = (
            s.execute(select(Upload).order_by(desc(Upload.uploaded_at)).limit(limit))
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "filename": r.filename,
                "sheet": r.sheet,
                "sha16": r.sha16,
                "size_bytes": r.size_bytes,
                "rows": r.rows,
                "cols": r.cols,
                "uploaded_at": r.uploaded_at.isoformat(),
            }
            for r in rows
        ]


@router.get("/preview_cached")
def preview_cached(sha16: str, sheet: str | None = None) -> dict[str, Any]:
    key = _preview_cache_key(sha16, sheet)
    cached = redis_sync.get(key)
    if not cached:
        raise HTTPException(404, f"No cached preview for digest={sha16} sheet={sheet!r}")
    import json

    data = json.loads(cached)
    data["cached"] = True
    return data


@router.delete("/preview_cached")
def delete_preview_cached(sha16: str, sheet: str | None = None) -> dict[str, Any]:
    key = _preview_cache_key(sha16, sheet)
    removed = bool(redis_sync.delete(key))
    with session_scope() as s:
        stmt = select(Upload).where(Upload.sha16 == sha16)
        if sheet:
            stmt = stmt.where(Upload.sheet == sheet)
        rows = s.execute(stmt).scalars().all()
        deleted_rows = 0
        for row in rows:
            s.delete(row)
            deleted_rows += 1
    return {"ok": True, "cache_removed": removed, "deleted_records": deleted_rows}


@router.delete("/preview_cached/all")
def delete_all_cached_previews() -> dict[str, Any]:
    removed = 0
    keys = list(redis_sync.scan_iter(match="dawn:dev:preview:*"))
    if keys:
        removed = redis_sync.delete(*keys)
    with session_scope() as s:
        result = s.execute(delete(Upload))
        deleted_rows = result.rowcount or 0
    return {"ok": True, "cache_removed": removed, "deleted_records": deleted_rows}
