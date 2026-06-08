from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class CreatorAccount(TimestampMixin, Base):
    __tablename__ = "creator_accounts"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "platform_account_id",
            name="uq_creator_platform_account",
        ),
        Index("ix_creator_status_next_collect", "monitoring_status", "next_collect_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_display_id: Mapped[str | None] = mapped_column(String(128), index=True)
    nickname: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_url: Mapped[str] = mapped_column(String(500), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    bio: Mapped[str | None] = mapped_column(Text)
    verified_info: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(128))
    group_name: Mapped[str | None] = mapped_column(String(128), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    monitor_interval_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    monitor_scope: Mapped[str] = mapped_column(
        String(32),
        default="creator_collection",
        nullable=False,
    )
    monitoring_status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )
    collector_type: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    collector_version: Mapped[str | None] = mapped_column(String(64))
    data_quality_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )
    last_content_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )
    last_collection_error: Mapped[str | None] = mapped_column(Text)
    baseline_content_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    content_baseline_established_at: Mapped[datetime | None] = mapped_column(DateTime)

    follower_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    following_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_like_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    content_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_collect_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    snapshots = relationship(
        "CreatorSnapshot",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
    collection_runs = relationship(
        "CollectionRun",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
    posts = relationship(
        "ContentPost",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
    alerts = relationship(
        "Alert",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
