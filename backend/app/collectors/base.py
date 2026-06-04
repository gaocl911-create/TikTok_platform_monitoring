from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models.creator import CreatorAccount


class CollectorError(RuntimeError):
    """Base error for explicit collector failures."""


class CollectorConfigurationError(CollectorError):
    """Raised when an account is assigned to an unsupported collector."""


class CollectorRenderError(CollectorError):
    """Raised when a public page cannot be rendered by the browser."""


class CollectorParseError(CollectorError):
    """Raised when expected public profile fields are unavailable."""


class CollectorValidationError(CollectorError):
    """Raised when the rendered account does not match the configured account."""


@dataclass(slots=True)
class CreatorProfile:
    nickname: str
    avatar_url: str | None
    bio: str | None
    verified_info: str | None
    location: str | None
    follower_count: int
    following_count: int
    total_like_count: int
    content_count: int


@dataclass(slots=True)
class ContentProfile:
    platform_content_id: str
    title: str
    summary: str | None
    content_type: str
    content_url: str
    cover_url: str | None
    published_at: datetime
    like_count: int
    comment_count: int
    collect_count: int
    share_count: int
    raw_data: dict | None = None


class CreatorCollector(Protocol):
    collector_type: str
    version: str
    content_status: str
    warnings: list[str]

    def fetch_creator_profile(self, creator: CreatorAccount) -> CreatorProfile: ...

    def fetch_content_posts(self, creator: CreatorAccount) -> list[ContentProfile]: ...
