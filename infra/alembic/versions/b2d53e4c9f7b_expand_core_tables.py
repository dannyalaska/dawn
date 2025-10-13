"""expand core tables for feeds, transforms, jobs, dq artifacts

Revision ID: b2d53e4c9f7b
Revises: a525995acbb9
Create Date: 2025-02-15 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2d53e4c9f7b"
down_revision: Union[str, Sequence[str], None] = "a525995acbb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("identifier", sa.String(length=128), nullable=False, unique=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("owner", sa.String(length=128), nullable=True),
        sa.Column("source_config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "feed_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "feed_id", sa.Integer(), sa.ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.Integer(), sa.ForeignKey("uploads.id"), nullable=True),
        sa.Column("sha16", sa.String(length=32), nullable=True),
        sa.Column("schema", sa.JSON(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("summary_markdown", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("feed_id", "version", name="uq_feed_versions_feed_version"),
    )

    op.create_table(
        "transforms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("feed_id", sa.Integer(), sa.ForeignKey("feeds.id"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "transform_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "transform_id",
            sa.Integer(),
            sa.ForeignKey("transforms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("dbt_model", sa.Text(), nullable=True),
        sa.Column("dry_run_report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "transform_id", "version", name="uq_transform_versions_transform_version"
        ),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "feed_version_id",
            sa.Integer(),
            sa.ForeignKey("feed_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "transform_version_id",
            sa.Integer(),
            sa.ForeignKey("transform_versions.id"),
            nullable=True,
        ),
        sa.Column("schedule", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("rows_in", sa.Integer(), nullable=True),
        sa.Column("rows_out", sa.Integer(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("logs", sa.JSON(), nullable=True),
    )

    op.create_table(
        "dq_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "feed_version_id",
            sa.Integer(),
            sa.ForeignKey("feed_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("column_name", sa.String(length=128), nullable=True),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "dq_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey("dq_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_run_id",
            sa.Integer(),
            sa.ForeignKey("job_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_feed_versions_feed_id", "feed_versions", ["feed_id"])
    op.create_index("ix_transform_versions_transform_id", "transform_versions", ["transform_id"])
    op.create_index("ix_jobs_feed_version_id", "jobs", ["feed_version_id"])
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_index("ix_dq_rules_feed_version_id", "dq_rules", ["feed_version_id"])
    op.create_index("ix_dq_results_rule_id", "dq_results", ["rule_id"])
    op.create_index("ix_dq_results_job_run_id", "dq_results", ["job_run_id"])


def downgrade() -> None:
    op.drop_index("ix_dq_results_job_run_id", table_name="dq_results")
    op.drop_index("ix_dq_results_rule_id", table_name="dq_results")
    op.drop_table("dq_results")

    op.drop_index("ix_dq_rules_feed_version_id", table_name="dq_rules")
    op.drop_table("dq_rules")

    op.drop_index("ix_job_runs_job_id", table_name="job_runs")
    op.drop_table("job_runs")

    op.drop_index("ix_jobs_feed_version_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_transform_versions_transform_id", table_name="transform_versions")
    op.drop_table("transform_versions")

    op.drop_table("transforms")

    op.drop_index("ix_feed_versions_feed_id", table_name="feed_versions")
    op.drop_table("feed_versions")

    op.drop_table("feeds")
