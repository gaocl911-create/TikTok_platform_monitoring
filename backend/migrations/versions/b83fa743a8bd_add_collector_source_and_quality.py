"""add collector source and quality

Revision ID: b83fa743a8bd
Revises: 687525cbdc3f
Create Date: 2026-06-04 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b83fa743a8bd"
down_revision: str | None = "687525cbdc3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "creator_accounts",
        sa.Column("collector_type", sa.String(length=32), server_default="mock", nullable=False),
    )
    op.add_column(
        "creator_accounts",
        sa.Column("collector_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "creator_accounts",
        sa.Column(
            "data_quality_status",
            sa.String(length=20),
            server_default="mock",
            nullable=False,
        ),
    )
    op.add_column(
        "creator_accounts",
        sa.Column(
            "last_content_status",
            sa.String(length=20),
            server_default="success",
            nullable=False,
        ),
    )
    op.add_column(
        "creator_accounts",
        sa.Column("last_collection_error", sa.Text(), nullable=True),
    )
    op.execute(
        "UPDATE creator_accounts "
        "SET collector_version = 'mock-v1', data_quality_status = 'mock', "
        "last_content_status = 'success'"
    )


def downgrade() -> None:
    op.drop_column("creator_accounts", "last_collection_error")
    op.drop_column("creator_accounts", "last_content_status")
    op.drop_column("creator_accounts", "data_quality_status")
    op.drop_column("creator_accounts", "collector_version")
    op.drop_column("creator_accounts", "collector_type")
