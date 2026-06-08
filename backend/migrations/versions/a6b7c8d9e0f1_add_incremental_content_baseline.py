"""add incremental content baseline

Revision ID: a6b7c8d9e0f1
Revises: 9f1b2c3d4e5f
Create Date: 2026-06-06 17:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "9f1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "creator_accounts",
        sa.Column("baseline_content_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "creator_accounts",
        sa.Column("content_baseline_established_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE creator_accounts "
        "SET baseline_content_ids = JSON_ARRAY() "
        "WHERE baseline_content_ids IS NULL"
    )
    op.alter_column(
        "creator_accounts",
        "baseline_content_ids",
        existing_type=sa.JSON(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("creator_accounts", "content_baseline_established_at")
    op.drop_column("creator_accounts", "baseline_content_ids")
