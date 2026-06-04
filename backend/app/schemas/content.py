from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
    published_at: datetime
    first_discovered_at: datetime
    latest_like_count: int
    latest_comment_count: int
    latest_collect_count: int
    latest_share_count: int
    status: str
    data_source: str
    creator: ContentCreatorRead


class ContentPostListResponse(BaseModel):
    items: list[ContentPostRead]
    total: int
    page: int
    page_size: int


class ContentSnapshotRead(UtcResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_id: int
    like_count: int
    comment_count: int
    collect_count: int
    share_count: int
    captured_at: datetime
