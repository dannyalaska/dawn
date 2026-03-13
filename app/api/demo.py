"""
Demo mode API endpoints.
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.core.auth import CurrentUser
from app.core.demo import get_demo_file_bytes, get_guided_tour_steps, seed_demo_workspace

router = APIRouter(prefix="/demo", tags=["demo"])
logger = logging.getLogger(__name__)


@router.get("/tour")
async def get_demo_tour() -> dict[str, list[dict[str, object]]]:
    return {"steps": get_guided_tour_steps()}


@router.get("/file")
async def get_demo_file() -> StreamingResponse:
    file_bytes = get_demo_file_bytes()
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=demo-support-tickets.xlsx"},
    )


@router.post("/seed")
async def seed_demo(current_user: CurrentUser) -> dict:
    """
    One-click demo workspace setup.
    Ingests 2 sheets from the built-in demo workbook and runs agent analysis
    on the ticketing dataset. Returns status and feed identifiers.
    """
    try:
        result = await run_in_threadpool(seed_demo_workspace, user_id=current_user.id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Demo seed failed: %s", exc)
        raise HTTPException(500, f"Demo seed failed: {exc}") from exc
    return result
