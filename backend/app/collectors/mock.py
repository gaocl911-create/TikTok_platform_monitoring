from datetime import timedelta
from hashlib import sha256

from app.collectors.base import ContentProfile, CreatorProfile
from app.models.base import utc_now
from app.models.creator import CreatorAccount


class MockCollector:
    """Generate deterministic but changing public metrics for the phase-two workflow."""

    collector_type = "mock"
    version = "mock-v1"
    content_status = "success"
    warnings: list[str] = []

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
            content_count=max(creator.content_count, base_content) + 1,
        )

    def fetch_content_posts(self, creator: CreatorAccount) -> list[ContentProfile]:
        seed = int(
            sha256(f"{creator.platform}:{creator.platform_account_id}".encode()).hexdigest()[:12],
            16,
        )
        latest_ordinal = creator.content_count
        now = utc_now()
        posts = []

        for offset in range(3):
            ordinal = latest_ordinal - offset
            if ordinal <= 0:
                continue
            engagement_round = max(1, latest_ordinal)
            base_likes = 80 + (seed + ordinal * 37) % 1500
            like_count = base_likes + engagement_round * (24 + ordinal % 17)
            comment_count = 8 + (seed + ordinal * 11) % 180 + engagement_round * 2
            collect_count = 5 + (seed + ordinal * 7) % 260 + engagement_round * 3
            share_count = 3 + (seed + ordinal * 5) % 100 + engagement_round
            platform_content_id = f"{creator.platform_account_id}-{ordinal}"

            posts.append(
                ContentProfile(
                    platform_content_id=platform_content_id,
                    title=f"{creator.nickname} 的第 {ordinal} 条公开内容",
                    summary="MockCollector 生成的内容动态，用于验证发现、快照与预警链路。",
                    content_type="video" if creator.platform == "douyin" else "note",
                    content_url=f"{creator.profile_url.rstrip('/')}/content/{platform_content_id}",
                    cover_url=None,
                    published_at=now - timedelta(hours=offset * 8),
                    like_count=like_count,
                    comment_count=comment_count,
                    collect_count=collect_count,
                    share_count=share_count,
                    raw_data={"source": "mock", "ordinal": ordinal},
                )
            )
        return posts
