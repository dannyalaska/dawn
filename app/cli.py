from __future__ import annotations

import json

import click

from app.core.auth import ensure_default_user
from app.core.runner_meta import gather_runner_stats


@click.group()
def cli() -> None:
    """Dawn CLI utilities."""


@cli.group()
def runner() -> None:
    """Inspect runner metadata."""


@runner.command("stats")
@click.option("--user-id", type=int, default=None, help="Target user id (defaults to local).")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "text"], case_sensitive=False),
    default="text",
)
def runner_stats(user_id: int | None, output_format: str) -> None:
    """Show counts for jobs and job runs."""
    if user_id is None:
        user_ctx = ensure_default_user()
        user_id = user_ctx.id
    stats = gather_runner_stats(user_id)
    if output_format == "json":
        click.echo(json.dumps(stats, indent=2))
        return
    click.echo(
        f"Jobs: total={stats['jobs']['total']} active={stats['jobs']['active']} "
        f"scheduled={stats['jobs']['scheduled']}"
    )
    last = stats["runs"]["last_run"]
    last_info = last["status"] if last and last.get("status") else "n/a"
    click.echo(
        "Runs: total={total} success={success} failed={failed} last_status={last}".format(
            total=stats["runs"]["total"],
            success=stats["runs"]["success"],
            failed=stats["runs"]["failed"],
            last=last_info,
        )
    )


if __name__ == "__main__":
    cli()
