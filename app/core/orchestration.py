from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from app.core.db import session_scope
from app.core.models import Feed, FeedVersion, Job, JobRun, Transform, TransformVersion

__all__ = ["JobError", "create_job", "get_job", "list_jobs", "execute_job", "get_job_run"]


class JobError(Exception):
    """Raised when job operations fail."""


@dataclass(frozen=True)
class JobRunContext:
    """Data required to record and summarise a job execution."""

    job_id: int
    run_id: int
    feed_rows: int
    dry_run_report: dict[str, Any] | None


def execute_job(job_id: int) -> dict[str, Any]:
    """Execute a job immediately and return the job + run payload."""
    ctx = _prepare_job_run(job_id)
    try:
        rows_in, rows_out, warnings, validation = _summarize_from_dry_run(
            ctx.dry_run_report,
            ctx.feed_rows,
        )
        status = "success"
        logs: list[dict[str, Any]] = [
            {
                "ts": datetime.utcnow().isoformat(),
                "level": "info",
                "message": f"Processed rows_in={rows_in} rows_out={rows_out}",
            }
        ]
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        rows_in = rows_out = 0
        warnings = [{"type": "error", "message": str(exc)}]
        validation = {}
        logs = [
            {
                "ts": datetime.utcnow().isoformat(),
                "level": "error",
                "message": f"Job execution failed: {exc}",
            }
        ]

    return _finalise_job_run(
        job_id=ctx.job_id,
        run_id=ctx.run_id,
        status=status,
        rows_in=rows_in,
        rows_out=rows_out,
        validation=validation,
        warnings=warnings,
        logs=logs,
    )


def create_job(
    *,
    name: str,
    feed_identifier: str,
    feed_version: int | None = None,
    transform_name: str | None = None,
    transform_version: int | None = None,
    schedule: str | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    with session_scope() as session:
        feed = (
            session.execute(select(Feed).where(Feed.identifier == feed_identifier))
            .scalars()
            .first()
        )
        if feed is None:
            raise JobError(f"Feed {feed_identifier!r} not found")

        feed_version_row = _resolve_feed_version(session, feed, feed_version)

        transform_version_id = None
        if transform_name:
            transform = (
                session.execute(select(Transform).where(Transform.name == transform_name))
                .scalars()
                .first()
            )
            if transform is None:
                raise JobError(f"Transform {transform_name!r} not found")
            tv = _resolve_transform_version(session, transform, transform_version)
            if tv is None:
                raise JobError(
                    f"Transform version not found for {transform_name!r} v={transform_version}"
                )
            transform_version_id = tv.id

        job = Job(
            name=name,
            feed_version_id=feed_version_row.id,
            transform_version_id=transform_version_id,
            schedule=schedule,
            is_active=is_active,
        )
        session.add(job)
        session.flush()
        return _serialize_job(session, job)


def get_job(job_id: int) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobError(f"Job id={job_id} not found")
        return _serialize_job(session, job)


def list_jobs() -> list[dict[str, Any]]:
    with session_scope() as session:
        jobs = session.execute(select(Job).order_by(desc(Job.created_at))).scalars().all()
        return [_serialize_job(session, job) for job in jobs]


def get_job_run(run_id: int) -> dict[str, Any]:
    with session_scope() as session:
        run = session.get(JobRun, run_id)
        if run is None:
            raise JobError(f"JobRun id={run_id} not found")
        return _job_run_to_dict(run)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _prepare_job_run(job_id: int) -> JobRunContext:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobError(f"Job id={job_id} not found")

        feed_version = session.get(FeedVersion, job.feed_version_id)
        if feed_version is None:
            raise JobError(f"Feed version id={job.feed_version_id} not found")

        dry_run_report: dict[str, Any] | None = None
        if job.transform_version_id is not None:
            transform_version = session.get(TransformVersion, job.transform_version_id)
            if transform_version is None:
                raise JobError(f"Transform version id={job.transform_version_id} not found")
            dry_run_report = dict(transform_version.dry_run_report or {})

        run = JobRun(job_id=job_id, status="running", started_at=datetime.utcnow())
        session.add(run)
        session.flush()

        return JobRunContext(
            job_id=job_id,
            run_id=run.id,
            feed_rows=int(feed_version.row_count or 0),
            dry_run_report=dry_run_report,
        )


def _summarize_from_dry_run(
    dry_run_report: dict[str, Any] | None,
    fallback_rows: int,
) -> tuple[int, int, list[dict[str, Any]], dict[str, Any]]:
    rows_in = fallback_rows
    rows_out = fallback_rows
    warnings: list[dict[str, Any]] = []
    validation: dict[str, Any] = {}

    if dry_run_report:
        rows_in = int(dry_run_report.get("rows_before", rows_in))
        rows_out = int(dry_run_report.get("rows_after", rows_in))
        removed = dry_run_report.get("columns_removed") or []
        if removed:
            warnings.append({"type": "columns_removed", "details": removed})
        validation["dry_run"] = dry_run_report

    return rows_in, rows_out, warnings, validation


def _finalise_job_run(
    *,
    job_id: int,
    run_id: int,
    status: str,
    rows_in: int,
    rows_out: int,
    validation: dict[str, Any],
    warnings: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> dict[str, Any]:
    finished = datetime.utcnow()
    with session_scope() as session:
        run = session.get(JobRun, run_id)
        if run is None:
            raise JobError(f"JobRun id={run_id} disappeared")
        run.status = status
        run.finished_at = finished
        run.rows_in = rows_in
        run.rows_out = rows_out
        run.warnings = warnings
        run.validation = validation
        run.logs = logs
        run_dict = _job_run_to_dict(run)

        job = session.get(Job, job_id)
        if job is None:
            raise JobError(f"Job id={job_id} not found during finalisation")
        job_dict = _serialize_job(session, job)

    return {"job": job_dict, "run": run_dict}


def _resolve_feed_version(session, feed: Feed, version: int | None) -> FeedVersion:
    stmt = select(FeedVersion).where(FeedVersion.feed_id == feed.id)
    if version is not None:
        stmt = stmt.where(FeedVersion.version == version)
    stmt = stmt.order_by(desc(FeedVersion.version)).limit(1)
    feed_version = session.execute(stmt).scalars().first()
    if feed_version is None:
        raise JobError(f"No feed version found for feed={feed.identifier!r} version={version}")
    return feed_version


def _resolve_transform_version(
    session, transform: Transform, version: int | None
) -> TransformVersion | None:
    stmt = select(TransformVersion).where(TransformVersion.transform_id == transform.id)
    if version is not None:
        stmt = stmt.where(TransformVersion.version == version)
    stmt = stmt.order_by(desc(TransformVersion.version)).limit(1)
    return session.execute(stmt).scalars().first()


def _serialize_job(session, job: Job) -> dict[str, Any]:
    feed_version = session.get(FeedVersion, job.feed_version_id)
    transform_version = (
        session.get(TransformVersion, job.transform_version_id)
        if job.transform_version_id
        else None
    )
    feed = session.get(Feed, feed_version.feed_id) if feed_version else None
    last_run = (
        session.execute(
            select(JobRun).where(JobRun.job_id == job.id).order_by(desc(JobRun.started_at)).limit(1)
        )
        .scalars()
        .first()
    )
    return {
        "id": job.id,
        "name": job.name,
        "feed": feed.identifier if feed else None,
        "feed_version": feed_version.version if feed_version else None,
        "transform_version": transform_version.version if transform_version else None,
        "schedule": job.schedule,
        "is_active": job.is_active,
        "created_at": job.created_at.isoformat(),
        "last_run": _job_run_to_dict(last_run) if last_run else None,
    }


def _job_run_to_dict(job_run: JobRun | None) -> dict[str, Any]:
    if job_run is None:
        return {}
    return {
        "id": job_run.id,
        "status": job_run.status,
        "started_at": job_run.started_at.isoformat(),
        "finished_at": job_run.finished_at.isoformat() if job_run.finished_at else None,
        "rows_in": job_run.rows_in,
        "rows_out": job_run.rows_out,
        "warnings": job_run.warnings or [],
        "validation": job_run.validation or {},
        "logs": job_run.logs or [],
    }
