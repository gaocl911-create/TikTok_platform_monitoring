"""add phase 4.5 observability

Revision ID: e2644d18a7bf
Revises: c41a9e71f36d
Create Date: 2026-06-04 18:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2644d18a7bf"
down_revision: str | None = "c41a9e71f36d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collection_runs",
        sa.Column("trigger_source", sa.String(length=20), server_default="manual", nullable=False),
    )
    op.add_column(
        "collection_runs",
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("collection_runs", sa.Column("collector_type", sa.String(length=32)))
    op.add_column("collection_runs", sa.Column("error_type", sa.String(length=64)))
    op.add_column("collection_runs", sa.Column("duration_ms", sa.Integer()))
    op.add_column(
        "content_posts",
        sa.Column("metrics_status", sa.String(length=20), server_default="success", nullable=False),
    )
    op.alter_column(
        "content_posts",
        "published_at",
        existing_type=sa.DateTime(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM content_posts WHERE published_at IS NULL")
    op.alter_column(
        "content_posts",
        "published_at",
        existing_type=sa.DateTime(),
        nullable=False,
    )
    op.drop_column("content_posts", "metrics_status")
    op.drop_column("collection_runs", "duration_ms")
    op.drop_column("collection_runs", "error_type")
    op.drop_column("collection_runs", "collector_type")
    op.drop_column("collection_runs", "attempt")
    op.drop_column("collection_runs", "trigger_source")
