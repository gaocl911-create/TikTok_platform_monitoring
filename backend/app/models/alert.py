from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import utc_now


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_alert_dedupe_key"),
        Index("ix_alert_status_triggered", "status", "triggered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creator_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_posts.id", ondelete="CASCADE"),
        index=True,
    )
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"),
        index=True,
    )
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unread", nullable=False)
    notification_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )
    notification_error: Mapped[str | None] = mapped_column(Text)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)

    creator = relationship("CreatorAccount", back_populates="alerts")
    content = relationship("ContentPost", back_populates="alerts")
    rule = relationship("AlertRule", back_populates="alerts")
