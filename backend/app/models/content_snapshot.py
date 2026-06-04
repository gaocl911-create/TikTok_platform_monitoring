from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ContentSnapshot(Base):
    __tablename__ = "content_snapshots"
    __table_args__ = (Index("ix_content_snapshot_content_time", "content_id", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("content_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    like_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    comment_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    collect_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    share_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    content = relationship("ContentPost", back_populates="snapshots")
