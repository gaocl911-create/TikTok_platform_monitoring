from hashlib import sha256

from app.collectors.base import CreatorProfile
from app.models.creator import CreatorAccount


class MockCollector:
    """Generate deterministic but changing public metrics for the phase-two workflow."""

    def fetch_creator_profile(self, creator: CreatorAccount) -> CreatorProfile:
        seed = int(
            sha256(f"{creator.platform}:{creator.platform_account_id}".encode()).hexdigest()[:12],
            16,
        )
        base_followers = 1_000 + seed % 90_000
        base_following = 30 + seed % 500
        base_likes = base_followers * (3 + seed % 12)
        base_content = 10 + seed % 180

        follower_increment = 3 + seed % 21
        like_increment = 20 + seed % 240

        return CreatorProfile(
            nickname=creator.nickname,
            avatar_url=creator.avatar_url,
            bio=creator.bio or "MockCollector 生成的公开资料，用于验证监控链路。",
            verified_info=creator.verified_info,
            location=creator.location or "公开地区待接入",
            follower_count=max(creator.follower_count, base_followers) + follower_increment,
            following_count=max(creator.following_count, base_following),
            total_like_count=max(creator.total_like_count, base_likes) + like_increment,
            content_count=max(creator.content_count, base_content),
        )
