"""fix future tikhub publish times

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-06-09 16:40:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE content_posts
        SET published_at = DATE_SUB(published_at, INTERVAL 8 HOUR)
        WHERE data_source = 'tikhub_douyin'
          AND published_at > UTC_TIMESTAMP()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE content_posts
        SET published_at = DATE_ADD(published_at, INTERVAL 8 HOUR)
        WHERE data_source = 'tikhub_douyin'
          AND published_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 8 HOUR)
          AND published_at <= UTC_TIMESTAMP()
        """
    )
