"""add source to snapshots and content

Revision ID: c41a9e71f36d
Revises: b83fa743a8bd
Create Date: 2026-06-04 16:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c41a9e71f36d"
down_revision: str | None = "b83fa743a8bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "creator_snapshots",
        sa.Column("collector_type", sa.String(length=32), server_default="mock", nullable=False),
    )
    op.add_column(
        "creator_snapshots",
        sa.Column(
            "data_quality_status",
            sa.String(length=20),
            server_default="mock",
            nullable=False,
        ),
    )
    op.add_column(
        "content_posts",
        sa.Column("data_source", sa.String(length=32), server_default="mock", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("content_posts", "data_source")
    op.drop_column("creator_snapshots", "data_quality_status")
    op.drop_column("creator_snapshots", "collector_type")
