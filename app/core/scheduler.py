"""Job scheduler using APScheduler for automated feed processing."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.db import session_scope
from app.core.models import Job
from app.core.orchestration import execute_job

logger = logging.getLogger(__name__)


class JobScheduler:
    """Manages scheduled job execution using APScheduler."""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,  # Combine missed runs
                "max_instances": 1,  # One instance per job at a time
                "misfire_grace_time": 300,  # 5 min grace period
            }
        )
        self._job_map: dict[int, str] = {}  # job_id -> apscheduler_job_id

    def start(self) -> None:
        """Start the scheduler and load all active jobs."""
        if self.scheduler.running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting job scheduler")
        self.scheduler.start()
        self._load_jobs()
        logger.info(f"Scheduler started with {len(self._job_map)} jobs")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self.scheduler.running:
            return

        logger.info("Stopping job scheduler")
        self.scheduler.shutdown(wait=True)
        self._job_map.clear()
        logger.info("Scheduler stopped")

    def _load_jobs(self) -> None:
        """Load all active scheduled jobs from database."""
        with session_scope() as session:
            jobs = (
                session.execute(
                    select(Job).where(Job.is_active == True, Job.schedule.isnot(None))  # noqa: E712
                )
                .scalars()
                .all()
            )

            for job in jobs:
                try:
                    self._add_job(job.id, job.schedule)  # type: ignore[arg-type]
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"Failed to schedule job {job.id}: {exc}")

    def _add_job(self, job_id: int, cron_expr: str) -> None:
        """Add a job to the scheduler.

        Args:
            job_id: Database job ID
            cron_expr: Cron expression (e.g., "0 2 * * *")
        """
        # Parse cron expression
        try:
            parts = cron_expr.split()
            if len(parts) != 5:  # noqa: PLR2004
                raise ValueError(f"Invalid cron format: {cron_expr}")

            minute, hour, day, month, day_of_week = parts
            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            )
        except Exception as exc:
            logger.error(f"Invalid cron expression '{cron_expr}' for job {job_id}: {exc}")
            raise

        # Add to scheduler
        apscheduler_job = self.scheduler.add_job(
            func=self._run_job,
            trigger=trigger,
            args=[job_id],
            id=f"dawn_job_{job_id}",
            name=f"Job {job_id}",
            replace_existing=True,
        )

        self._job_map[job_id] = apscheduler_job.id
        logger.info(f"Scheduled job {job_id} with cron '{cron_expr}'")

    def _run_job(self, job_id: int) -> None:
        """Execute a scheduled job.

        Args:
            job_id: Database job ID
        """
        logger.info(f"Starting scheduled execution of job {job_id}")
        start_time = datetime.utcnow()

        try:
            result = execute_job(job_id)
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Job {job_id} completed successfully in {duration:.1f}s: "
                f"{result.get('rows_out', 0)} rows processed"
            )
        except Exception as exc:  # noqa: BLE001
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Job {job_id} failed after {duration:.1f}s: {exc}", exc_info=True)

    def add_job(self, job_id: int, cron_expr: str) -> None:
        """Add or update a scheduled job.

        Args:
            job_id: Database job ID
            cron_expr: Cron expression
        """
        if not self.scheduler.running:
            logger.warning("Scheduler not running, job will be loaded on next start")
            return

        # Remove existing if present
        self.remove_job(job_id)

        # Add new schedule
        self._add_job(job_id, cron_expr)

    def remove_job(self, job_id: int) -> None:
        """Remove a job from the scheduler.

        Args:
            job_id: Database job ID
        """
        apscheduler_job_id = self._job_map.pop(job_id, None)
        if apscheduler_job_id:
            try:
                self.scheduler.remove_job(apscheduler_job_id)
                logger.info(f"Removed job {job_id} from scheduler")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to remove job {job_id}: {exc}")

    def pause_job(self, job_id: int) -> None:
        """Pause a scheduled job.

        Args:
            job_id: Database job ID
        """
        apscheduler_job_id = self._job_map.get(job_id)
        if apscheduler_job_id:
            try:
                self.scheduler.pause_job(apscheduler_job_id)
                logger.info(f"Paused job {job_id}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to pause job {job_id}: {exc}")

    def resume_job(self, job_id: int) -> None:
        """Resume a paused job.

        Args:
            job_id: Database job ID
        """
        apscheduler_job_id = self._job_map.get(job_id)
        if apscheduler_job_id:
            try:
                self.scheduler.resume_job(apscheduler_job_id)
                logger.info(f"Resumed job {job_id}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to resume job {job_id}: {exc}")

    def get_next_run_time(self, job_id: int) -> datetime | None:
        """Get the next scheduled run time for a job.

        Args:
            job_id: Database job ID

        Returns:
            Next run datetime or None if not scheduled
        """
        apscheduler_job_id = self._job_map.get(job_id)
        if apscheduler_job_id:
            try:
                job = self.scheduler.get_job(apscheduler_job_id)
                return job.next_run_time if job else None
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to get next run time for job {job_id}: {exc}")
        return None

    def list_scheduled_jobs(self) -> list[dict[str, Any]]:
        """List all currently scheduled jobs.

        Returns:
            List of job info dictionaries
        """
        jobs = []
        for job_id, apscheduler_job_id in self._job_map.items():
            try:
                apjob = self.scheduler.get_job(apscheduler_job_id)
                if apjob:
                    jobs.append(
                        {
                            "job_id": job_id,
                            "next_run": (
                                apjob.next_run_time.isoformat() if apjob.next_run_time else None
                            ),
                            "trigger": str(apjob.trigger),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to get info for job {job_id}: {exc}")

        return jobs


# Global scheduler instance
_scheduler: JobScheduler | None = None


def get_scheduler() -> JobScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = JobScheduler()
    return _scheduler


def start_scheduler() -> None:
    """Start the global scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler() -> None:
    """Stop the global scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
