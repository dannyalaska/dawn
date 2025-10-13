from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.orchestration import (
    JobError,
    create_job,
    get_job,
    list_jobs,
    run_job,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    name: str = Field(min_length=3)
    feed_identifier: str = Field(min_length=2)
    feed_version: int | None = None
    transform_name: str | None = None
    transform_version: int | None = None
    schedule: str | None = None
    is_active: bool = True


@router.get("")
def jobs_index() -> dict[str, Any]:
    return {"jobs": list_jobs()}


@router.post("")
def jobs_create(payload: JobCreateRequest) -> dict[str, Any]:
    try:
        job = create_job(
            name=payload.name,
            feed_identifier=payload.feed_identifier,
            feed_version=payload.feed_version,
            transform_name=payload.transform_name,
            transform_version=payload.transform_version,
            schedule=payload.schedule,
            is_active=payload.is_active,
        )
    except JobError as exc:
        raise HTTPException(400, str(exc)) from exc
    return job


@router.get("/{job_id}")
def job_detail(job_id: int) -> dict[str, Any]:
    try:
        job = get_job(job_id)
    except JobError as exc:
        raise HTTPException(404, str(exc)) from exc
    return job


@router.post("/{job_id}/run")
def job_run(job_id: int) -> dict[str, Any]:
    try:
        result = run_job(job_id)
    except JobError as exc:
        raise HTTPException(404, str(exc)) from exc
    return result
