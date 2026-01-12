"""
Demo mode API endpoints.
"""

from __future__ import annotations

import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.demo import get_demo_file_bytes, get_guided_tour_steps

router = APIRouter(prefix="/demo", tags=["demo"])


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
