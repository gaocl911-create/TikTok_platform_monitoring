from dataclasses import dataclass
from typing import Protocol

from app.models.creator import CreatorAccount


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


class CreatorCollector(Protocol):
    def fetch_creator_profile(self, creator: CreatorAccount) -> CreatorProfile: ...
