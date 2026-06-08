"""add monitor scope

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-06-08 09:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "creator_accounts",
        sa.Column(
            "monitor_scope",
            sa.String(length=32),
            server_default="creator_collection",
            nullable=False,
        ),
    )
    op.alter_column("creator_accounts", "monitor_scope", server_default=None)


def downgrade() -> None:
    op.drop_column("creator_accounts", "monitor_scope")
