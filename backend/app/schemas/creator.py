from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["douyin", "xiaohongshu"]
Priority = Literal["high", "normal", "low"]
MonitoringStatus = Literal["active", "paused"]


class CreatorCreate(BaseModel):
    platform: Platform
    platform_account_id: str = Field(min_length=1, max_length=128)
    nickname: str = Field(min_length=1, max_length=128)
    profile_url: str = Field(min_length=1, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=1000)
    bio: str | None = None
    group_name: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list)
    priority: Priority = "normal"
    monitor_interval_minutes: int = Field(default=60, ge=5, le=10080)


class CreatorUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=128)
    profile_url: str | None = Field(default=None, min_length=1, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=1000)
    bio: str | None = None
    group_name: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = None
    priority: Priority | None = None
    monitor_interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    monitoring_status: MonitoringStatus | None = None


class CreatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    platform_account_id: str
    nickname: str
    profile_url: str
    avatar_url: str | None
    bio: str | None
    verified_info: str | None
    location: str | None
    group_name: str | None
    tags: list[str]
    priority: str
    monitor_interval_minutes: int
    monitoring_status: str
    follower_count: int
    following_count: int
    total_like_count: int
    content_count: int
    last_collected_at: datetime | None
    next_collect_at: datetime | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class CreatorListResponse(BaseModel):
    items: list[CreatorRead]
    total: int
    page: int
    page_size: int


class CreatorSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    follower_count: int
    following_count: int
    total_like_count: int
    content_count: int
    captured_at: datetime


class CollectionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    task_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    result_summary: dict | None


class CollectionResult(BaseModel):
    creator: CreatorRead
    snapshot: CreatorSnapshotRead
    run: CollectionRunRead
