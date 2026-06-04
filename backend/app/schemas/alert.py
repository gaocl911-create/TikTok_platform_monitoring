from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import UtcResponseModel

AlertType = Literal["new_content", "content_like_growth"]


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    alert_type: AlertType
    conditions_json: dict = Field(default_factory=dict)
    notification_channels_json: list[str] = Field(default_factory=lambda: ["webhook"])
    is_enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    conditions_json: dict | None = None
    notification_channels_json: list[str] | None = None
    is_enabled: bool | None = None


class AlertRuleRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    alert_type: str
    conditions_json: dict
    notification_channels_json: list[str]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class AlertRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    content_id: int | None
    rule_id: int | None
    alert_type: str
    severity: str
    title: str
    message: str
    status: str
    notification_status: str
    notification_error: str | None
    triggered_at: datetime
    read_at: datetime | None


class AlertListResponse(BaseModel):
    items: list[AlertRead]
    total: int
    unread_count: int
    page: int
    page_size: int
