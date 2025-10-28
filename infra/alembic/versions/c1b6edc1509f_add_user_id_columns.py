"""Add user_id columns to core tables for per-user scoping.

Revision ID: c1b6edc1509f
Revises: b2d53e4c9f7b
Create Date: 2024-11-24 17:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c1b6edc1509f"
down_revision: Union[str, Sequence[str], None] = "b2d53e4c9f7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the migration."""
    with op.batch_alter_table("uploads", schema=None) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_uploads_user_id", ["user_id"])
        batch.create_foreign_key(
            "fk_uploads_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("feeds", schema=None) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_feeds_user_id", ["user_id"])
        batch.create_foreign_key(
            "fk_feeds_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("feed_versions", schema=None) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_feed_versions_user_id", ["user_id"])
        batch.create_foreign_key(
            "fk_feed_versions_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("transforms", schema=None) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_transforms_user_id", ["user_id"])
        batch.create_foreign_key(
            "fk_transforms_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("transform_versions", schema=None) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_transform_versions_user_id", ["user_id"])
        batch.create_foreign_key(
            "fk_transform_versions_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("jobs", schema=None) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_jobs_user_id", ["user_id"])
        batch.create_foreign_key(
            "fk_jobs_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("job_runs", schema=None) as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_job_runs_user_id", ["user_id"])
        batch.create_foreign_key(
            "fk_job_runs_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Revert the migration."""
    with op.batch_alter_table("job_runs", schema=None) as batch:
        batch.drop_index("ix_job_runs_user_id")
        batch.drop_constraint("fk_job_runs_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("jobs", schema=None) as batch:
        batch.drop_index("ix_jobs_user_id")
        batch.drop_constraint("fk_jobs_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("transform_versions", schema=None) as batch:
        batch.drop_index("ix_transform_versions_user_id")
        batch.drop_constraint("fk_transform_versions_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("transforms", schema=None) as batch:
        batch.drop_index("ix_transforms_user_id")
        batch.drop_constraint("fk_transforms_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("feed_versions", schema=None) as batch:
        batch.drop_index("ix_feed_versions_user_id")
        batch.drop_constraint("fk_feed_versions_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("feeds", schema=None) as batch:
        batch.drop_index("ix_feeds_user_id")
        batch.drop_constraint("fk_feeds_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")

    with op.batch_alter_table("uploads", schema=None) as batch:
        batch.drop_index("ix_uploads_user_id")
        batch.drop_constraint("fk_uploads_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
