"""replace tikomni account collectors with tikhub

Revision ID: d8e9f0a1b2c3
Revises: b7c8d9e0f1a2
Create Date: 2026-06-09 15:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE creator_accounts
        SET collector_type = 'tikhub_douyin',
            collector_version = 'tikhub-douyin-v1'
        WHERE collector_type = 'tikomni_douyin'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE creator_accounts
        SET collector_type = 'tikomni_douyin',
            collector_version = 'tikomni-douyin-v1'
        WHERE collector_type = 'tikhub_douyin'
          AND collector_version = 'tikhub-douyin-v1'
        """
    )
