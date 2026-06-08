from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import UtcResponseModel


class ContentCreatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    nickname: str


class ContentPostRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    platform_content_id: str
    title: str
    summary: str | None
    content_type: str
    content_url: str
    cover_url: str | None
    published_at: datetime | None
    first_discovered_at: datetime
    latest_like_count: int
    latest_comment_count: int
    latest_collect_count: int
    latest_share_count: int
    status: str
    data_source: str
    metrics_status: str
    creator: ContentCreatorRead


class ContentPostListResponse(BaseModel):
    items: list[ContentPostRead]
    total: int
    page: int
    page_size: int


class ContentLinkResolveRequest(BaseModel):
    platform: Literal["douyin", "xiaohongshu"] = "douyin"
    input_value: str = Field(min_length=1, max_length=1000)


class ContentLinkCreateRequest(ContentLinkResolveRequest):
    resolve_token: str | None = Field(default=None, max_length=128)
    creator_id: int | None = None
    group_name: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list)
    monitor_interval_minutes: int = Field(default=30, ge=5, le=10080)


class ContentCreatorPreview(BaseModel):
    platform_account_id: str
    platform_display_id: str | None
    nickname: str
    profile_url: str
    avatar_url: str | None
    bio: str | None
    location: str | None


class ContentWorkPreview(BaseModel):
    platform_content_id: str
    title: str
    summary: str | None
    content_type: str
    content_url: str
    cover_url: str | None
    published_at: datetime | None
    like_count: int
    comment_count: int
    collect_count: int
    share_count: int
    metrics_status: str


class ContentLinkResolveResponse(BaseModel):
    platform: str
    source_url: str
    resolve_token: str | None = None
    creator: ContentCreatorPreview
    content: ContentWorkPreview
    existing_creator_id: int | None = None
    existing_post_id: int | None = None
    warnings: list[str] = Field(default_factory=list)


class ContentLinkCreateResponse(BaseModel):
    post: ContentPostRead
    creator_created: bool
    post_created: bool
    run_id: int
    warnings: list[str] = Field(default_factory=list)


class ContentSnapshotRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_id: int
    like_count: int
    comment_count: int
    collect_count: int
    share_count: int
    captured_at: datetime
