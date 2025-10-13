from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.orchestration import (
    JobError,
    create_job,
    execute_job,
    get_job,
    list_jobs,
)
from app.core.scheduler import get_scheduler

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
        # Add to scheduler if active and has schedule
        if payload.is_active and payload.schedule:
            try:
                scheduler = get_scheduler()
                scheduler.add_job(job["id"], payload.schedule)
            except Exception as exc:  # noqa: BLE001
                # Log but don't fail - job is still created
                print(f"[jobs] Failed to schedule job {job['id']}: {exc}")
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
    """Manually trigger a job execution."""
    try:
        result = execute_job(job_id)
    except JobError as exc:
        raise HTTPException(404, str(exc)) from exc
    return result


@router.post("/{job_id}/pause")
def job_pause(job_id: int) -> dict[str, Any]:
    """Pause a scheduled job."""
    try:
        scheduler = get_scheduler()
        scheduler.pause_job(job_id)
        return {"status": "paused", "job_id": job_id}
    except Exception as exc:
        raise HTTPException(500, f"Failed to pause job: {exc}") from exc


@router.post("/{job_id}/resume")
def job_resume(job_id: int) -> dict[str, Any]:
    """Resume a paused job."""
    try:
        scheduler = get_scheduler()
        scheduler.resume_job(job_id)
        return {"status": "resumed", "job_id": job_id}
    except Exception as exc:
        raise HTTPException(500, f"Failed to resume job: {exc}") from exc


@router.get("/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    """Get scheduler status and list of scheduled jobs."""
    try:
        scheduler = get_scheduler()
        scheduled_jobs = scheduler.list_scheduled_jobs()
        return {
            "running": scheduler.scheduler.running,
            "scheduled_jobs": scheduled_jobs,
            "count": len(scheduled_jobs),
        }
    except Exception as exc:
        raise HTTPException(500, f"Failed to get scheduler status: {exc}") from exc
