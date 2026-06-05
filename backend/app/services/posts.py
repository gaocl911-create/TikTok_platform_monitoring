from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.collectors import ContentProfile
from app.models.content_post import ContentPost
from app.models.content_snapshot import ContentSnapshot
from app.models.creator import CreatorAccount


def sync_content_posts(
    db: Session,
    creator: CreatorAccount,
    profiles: list[ContentProfile],
    *,
    captured_at: datetime,
) -> tuple[list[ContentPost], list[tuple[ContentPost, ContentSnapshot, int]]]:
    platform_ids = [profile.platform_content_id for profile in profiles]
    if not platform_ids:
        return [], []
    query = select(ContentPost).where(
        ContentPost.creator_id == creator.id,
        ContentPost.platform_content_id.in_(platform_ids),
    )
    existing = {post.platform_content_id: post for post in db.scalars(query).all()}
    new_posts: list[ContentPost] = []
    snapshot_results: list[tuple[ContentPost, ContentSnapshot, int]] = []

    for profile in profiles:
        post = existing.get(profile.platform_content_id)
        previous_likes = 0
        if post is None:
            post = ContentPost(
                creator_id=creator.id,
                platform_content_id=profile.platform_content_id,
                title=profile.title,
                summary=profile.summary,
                content_type=profile.content_type,
                content_url=profile.content_url,
                cover_url=profile.cover_url,
                published_at=profile.published_at,
                first_discovered_at=captured_at,
                data_source=creator.collector_type,
                metrics_status=profile.metrics_status,
                raw_data_json=profile.raw_data,
            )
            db.add(post)
            db.flush()
            new_posts.append(post)
        else:
            previous_likes = post.latest_like_count
            post.title = profile.title
            post.summary = profile.summary
            post.content_url = profile.content_url
            post.cover_url = profile.cover_url
            post.data_source = creator.collector_type
            post.metrics_status = profile.metrics_status
            post.raw_data_json = profile.raw_data
            if profile.published_at is not None:
                post.published_at = profile.published_at

        if profile.metrics_status != "success":
            continue
        post.latest_like_count = max(previous_likes, profile.like_count)
        post.latest_comment_count = max(post.latest_comment_count, profile.comment_count)
        post.latest_collect_count = max(post.latest_collect_count, profile.collect_count)
        post.latest_share_count = max(post.latest_share_count, profile.share_count)

        snapshot = ContentSnapshot(
            content_id=post.id,
            like_count=post.latest_like_count,
            comment_count=post.latest_comment_count,
            collect_count=post.latest_collect_count,
            share_count=post.latest_share_count,
            captured_at=captured_at,
        )
        db.add(snapshot)
        db.flush()
        snapshot_results.append((post, snapshot, post.latest_like_count - previous_likes))

    return new_posts, snapshot_results


def get_post(db: Session, post_id: int) -> ContentPost | None:
    query = (
        select(ContentPost)
        .options(selectinload(ContentPost.creator))
        .where(ContentPost.id == post_id)
    )
    return db.scalar(query)


def list_posts(
    db: Session,
    *,
    page: int,
    page_size: int,
    creator_id: int | None = None,
    platform: str | None = None,
    search: str | None = None,
) -> tuple[list[ContentPost], int]:
    filters = []
    if creator_id:
        filters.append(ContentPost.creator_id == creator_id)
    if platform:
        filters.append(CreatorAccount.platform == platform)
    if search:
        keyword = f"%{search.strip()}%"
        filters.append(
            or_(
                ContentPost.title.like(keyword),
                ContentPost.summary.like(keyword),
                CreatorAccount.nickname.like(keyword),
            )
        )

    count_query = (
        select(func.count(ContentPost.id))
        .join(CreatorAccount, ContentPost.creator_id == CreatorAccount.id)
        .where(*filters)
    )
    total = db.scalar(count_query) or 0
    query = (
        select(ContentPost)
        .join(CreatorAccount, ContentPost.creator_id == CreatorAccount.id)
        .options(selectinload(ContentPost.creator))
        .where(*filters)
        .order_by(ContentPost.published_at.desc(), ContentPost.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(query).all()), total


def list_post_snapshots(
    db: Session,
    post_id: int,
    *,
    limit: int = 100,
) -> list[ContentSnapshot]:
    query = (
        select(ContentSnapshot)
        .where(ContentSnapshot.content_id == post_id)
        .order_by(ContentSnapshot.captured_at.desc())
        .limit(limit)
    )
    snapshots = list(db.scalars(query).all())
    snapshots.reverse()
    return snapshots
