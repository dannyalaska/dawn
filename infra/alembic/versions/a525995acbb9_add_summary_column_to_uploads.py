"""add summary column to uploads

Revision ID: a525995acbb9
Revises: 70c9cc06c819
Create Date: 2025-10-07 18:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a525995acbb9"
down_revision: Union[str, Sequence[str], None] = "70c9cc06c819"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("uploads", sa.Column("summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("uploads", "summary")
