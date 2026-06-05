from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, utc_now


class ContentPost(TimestampMixin, Base):
    __tablename__ = "content_posts"
    __table_args__ = (
        UniqueConstraint(
            "creator_id",
            "platform_content_id",
            name="uq_content_creator_platform_id",
        ),
        Index("ix_content_creator_published", "creator_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creator_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform_content_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(32), default="video", nullable=False)
    content_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    latest_like_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    latest_comment_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    latest_collect_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    latest_share_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    data_source: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    metrics_status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    raw_data_json: Mapped[dict | None] = mapped_column(JSON)

    creator = relationship("CreatorAccount", back_populates="posts")
    snapshots = relationship(
        "ContentSnapshot",
        back_populates="content",
        cascade="all, delete-orphan",
    )
    alerts = relationship("Alert", back_populates="content")
