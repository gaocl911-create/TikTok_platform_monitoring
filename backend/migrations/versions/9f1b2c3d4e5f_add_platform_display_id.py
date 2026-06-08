"""add platform display id

Revision ID: 9f1b2c3d4e5f
Revises: e2644d18a7bf
Create Date: 2026-06-06 17:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f1b2c3d4e5f"
down_revision: str | None = "e2644d18a7bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "creator_accounts",
        sa.Column("platform_display_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_creator_accounts_platform_display_id",
        "creator_accounts",
        ["platform_display_id"],
    )
    op.execute(
        "UPDATE creator_accounts "
        "SET platform_display_id = platform_account_id "
        "WHERE platform_display_id IS NULL "
        "AND platform_account_id NOT LIKE 'MS4w%'"
    )


def downgrade() -> None:
    op.drop_index("ix_creator_accounts_platform_display_id", table_name="creator_accounts")
    op.drop_column("creator_accounts", "platform_display_id")
