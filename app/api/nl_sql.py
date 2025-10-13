from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.nl2sql import nl_to_sql

router = APIRouter(prefix="/nl", tags=["nl2sql"])


class NLQueryRequest(BaseModel):
    question: str = Field(min_length=3)
    feed_identifiers: list[str] | None = None
    allow_writes: bool = False
    dialect: str = Field(default="postgres")
    explain: bool = False


@router.post("/sql")
def generate_sql(payload: NLQueryRequest) -> dict[str, Any]:
    result = nl_to_sql(
        payload.question,
        feed_identifiers=payload.feed_identifiers,
        allow_writes=payload.allow_writes,
        dialect=payload.dialect,
        explain=payload.explain,
    )
    if not result["validation"].get("ok", False):
        raise HTTPException(400, result)
    return result
