from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.db import session_scope
from app.core.models import Job, JobRun


def _count(session, stmt) -> int:
    return int(session.execute(stmt).scalar() or 0)


def gather_runner_stats(user_id: int) -> dict[str, Any]:
    with session_scope() as session:
        base_jobs = select(func.count()).select_from(Job).where(Job.user_id == user_id)
        total_jobs = _count(session, base_jobs)
        active_jobs = _count(session, base_jobs.where(Job.is_active.is_(True)))
        scheduled_jobs = _count(session, base_jobs.where(Job.schedule.is_not(None)))

        base_runs = select(func.count()).select_from(JobRun).where(JobRun.user_id == user_id)
        total_runs = _count(session, base_runs)
        success_runs = _count(session, base_runs.where(JobRun.status == "success"))
        failed_runs = _count(session, base_runs.where(JobRun.status == "failed"))

        last_run = (
            session.execute(
                select(JobRun)
                .where(JobRun.user_id == user_id)
                .order_by(JobRun.started_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        last_run_payload: dict[str, Any] = {
            "finished_at": None,
            "status": None,
            "duration_seconds": None,
        }
        if last_run:
            last_run_payload["finished_at"] = (
                last_run.finished_at.isoformat() if last_run.finished_at else None
            )
            last_run_payload["status"] = last_run.status
            if last_run.started_at and last_run.finished_at:
                delta: timedelta = last_run.finished_at - last_run.started_at
                last_run_payload["duration_seconds"] = round(delta.total_seconds(), 3)

    return {
        "jobs": {
            "total": total_jobs,
            "active": active_jobs,
            "scheduled": scheduled_jobs,
        },
        "runs": {
            "total": total_runs,
            "success": success_runs,
            "failed": failed_runs,
            "last_run": last_run_payload,
        },
    }
