from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class AlertRule(TimestampMixin, Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    conditions_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notification_channels_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    alerts = relationship("Alert", back_populates="rule")
