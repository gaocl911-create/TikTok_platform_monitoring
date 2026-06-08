from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import UtcResponseModel
from app.utils.profile_urls import normalize_profile_url

Platform = Literal["douyin", "xiaohongshu"]
Priority = Literal["high", "normal", "low"]
MonitoringStatus = Literal["active", "paused"]
CollectorType = Literal["mock", "douyin_public_web", "tikomni_douyin"]


class CreatorCreate(BaseModel):
    platform: Platform
    platform_account_id: str = Field(min_length=1, max_length=128)
    platform_display_id: str | None = Field(default=None, max_length=128)
    nickname: str = Field(min_length=1, max_length=128)
    profile_url: str = Field(min_length=1, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=1000)
    bio: str | None = None
    verified_info: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list)
    priority: Priority = "normal"
    monitor_interval_minutes: int = Field(default=30, ge=5, le=10080)
    collector_type: CollectorType = "mock"
    follower_count: int = Field(default=0, ge=0)
    following_count: int = Field(default=0, ge=0)
    total_like_count: int = Field(default=0, ge=0)
    content_count: int = Field(default=0, ge=0)
    profile_resolved: bool = False

    @field_validator("profile_url", mode="before")
    @classmethod
    def normalize_profile_url_field(cls, value: str) -> str:
        return normalize_profile_url(value)

    @model_validator(mode="after")
    def validate_collector_type(self) -> Self:
        if (
            self.collector_type in {"douyin_public_web", "tikomni_douyin"}
            and self.platform != "douyin"
        ):
            raise ValueError("抖音真实采集器只能用于抖音账号")
        return self


class CreatorProfileResolveRequest(BaseModel):
    platform: Platform
    input_value: str = Field(min_length=1, max_length=1000)


class CreatorProfileResolveResponse(BaseModel):
    platform: Platform
    platform_account_id: str
    platform_display_id: str | None = None
    nickname: str
    profile_url: str
    avatar_url: str | None = None
    bio: str | None = None
    verified_info: str | None = None
    location: str | None = None
    follower_count: int
    following_count: int
    total_like_count: int
    content_count: int
    collector_type: CollectorType
    sec_user_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CreatorUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=128)
    platform_display_id: str | None = Field(default=None, max_length=128)
    profile_url: str | None = Field(default=None, min_length=1, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=1000)
    bio: str | None = None
    group_name: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = None
    priority: Priority | None = None
    monitor_interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    monitoring_status: MonitoringStatus | None = None
    collector_type: CollectorType | None = None

    @field_validator("profile_url", mode="before")
    @classmethod
    def normalize_profile_url_field(cls, value: str | None) -> str | None:
        return normalize_profile_url(value) if value is not None else None


class CreatorRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    platform_account_id: str
    platform_display_id: str | None
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
    collector_type: str
    collector_version: str | None
    data_quality_status: str
    last_content_status: str
    last_collection_error: str | None
    content_baseline_established_at: datetime | None
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


class CreatorSnapshotRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    follower_count: int
    following_count: int
    total_like_count: int
    content_count: int
    collector_type: str
    data_quality_status: str
    captured_at: datetime


class CollectionRunCreatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str
    platform: str


class CollectionRunRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    task_type: str
    status: str
    trigger_source: str
    attempt: int
    collector_type: str | None
    error_type: str | None
    duration_ms: int | None
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    result_summary: dict | None
    creator: CollectionRunCreatorRead


class CollectionResult(BaseModel):
    creator: CreatorRead
    snapshot: CreatorSnapshotRead
    run: CollectionRunRead


class CollectionRetryQueued(BaseModel):
    creator_id: int
    task_id: str
    status: Literal["queued"]
    retry_after_seconds: int
    message: str


class CollectionRunListResponse(BaseModel):
    items: list[CollectionRunRead]
    total: int
    page: int
    page_size: int
