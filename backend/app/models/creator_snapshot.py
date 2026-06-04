from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CreatorSnapshot(Base):
    __tablename__ = "creator_snapshots"
    __table_args__ = (Index("ix_creator_snapshot_creator_time", "creator_id", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creator_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    follower_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    following_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_like_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_count: Mapped[int] = mapped_column(Integer, nullable=False)
    collector_type: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    data_quality_status: Mapped[str] = mapped_column(String(20), default="mock", nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    creator = relationship("CreatorAccount", back_populates="snapshots")
