import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.collectors import (
    CollectorConfigurationError,
    ContentProfile,
    TikHubDouyinWorkResolver,
    TikHubResolvedCreator,
    TikHubResolvedWork,
)
from app.core.config import settings
from app.models.base import utc_now
from app.models.collection_run import CollectionRun
from app.models.content_post import ContentPost
from app.models.content_snapshot import ContentSnapshot
from app.models.creator import CreatorAccount
from app.models.creator_snapshot import CreatorSnapshot


@dataclass(slots=True)
class LinkedContentResult:
    post: ContentPost
    creator: CreatorAccount
    creator_created: bool
    post_created: bool
    run: CollectionRun
    warnings: list[str]


_RESOLVE_CACHE_TTL_SECONDS = 600
_RESOLVE_CACHE_PREFIX = "creator-monitor:single-work-resolve"
_LOCAL_RESOLVE_CACHE: dict[str, tuple[datetime, str]] = {}


def resolve_content_link(
    db: Session,
    *,
    platform: str,
    input_value: str,
    data_provider: str | None = None,
) -> tuple[TikHubResolvedWork, dict, list[str]]:
    if platform != "douyin":
        raise CollectorConfigurationError("单作品链接添加第一版只支持抖音")
    started_at = utc_now()
    provider = _normalize_single_work_provider(data_provider)
    resolver = TikHubDouyinWorkResolver(
        spent_today_usd=_tikhub_spent_today_usd(db, started_at),
    )
    resolved = resolver.resolve(input_value)
    return resolved, resolver.usage_summary(), list(resolver.warnings)


def cache_resolved_content_link(
    *,
    platform: str,
    input_value: str,
    data_provider: str | None,
    resolved: TikHubResolvedWork,
    usage_summary: dict,
    warnings: list[str],
) -> str | None:
    token = secrets.token_urlsafe(24)
    provider = _normalize_single_work_provider(data_provider)
    payload = json.dumps(
        {
            "platform": platform,
            "data_provider": provider,
            "input_hash": _cache_input_hash(platform, input_value, provider),
            "resolved": _resolved_work_to_cache_payload(resolved),
            "usage_summary": usage_summary,
            "warnings": warnings,
            "cached_at": utc_now().isoformat(),
        },
        ensure_ascii=False,
        default=str,
    )
    expires_at = utc_now() + timedelta(seconds=_RESOLVE_CACHE_TTL_SECONDS)
    _remember_local_cache(token, expires_at, payload)
    try:
        client = _resolve_cache_client()
        client.setex(_resolve_cache_key(token), _RESOLVE_CACHE_TTL_SECONDS, payload)
        client.close()
    except RedisError:
        return token
    return token


def add_content_from_link(
    db: Session,
    *,
    platform: str,
    input_value: str,
    creator_id: int | None = None,
    group_name: str | None = None,
    tags: list[str] | None = None,
    monitor_interval_minutes: int = 30,
    resolve_token: str | None = None,
    data_provider: str | None = None,
) -> LinkedContentResult:
    started_at = utc_now()
    provider = _normalize_single_work_provider(data_provider)
    cached = _load_cached_resolved_content_link(
        platform=platform,
        input_value=input_value,
        data_provider=provider,
        resolve_token=resolve_token,
    )
    if cached is None:
        resolved, usage_summary, warnings = resolve_content_link(
            db,
            platform=platform,
            input_value=input_value,
            data_provider=provider,
        )
        cache_hit = False
        consumed_resolve_token = None
    else:
        resolved, usage_summary, warnings = cached
        usage_summary = {
            **usage_summary,
            f"{provider}_cache_hit": True,
            "resolve_phase_cost_attributed": True,
        }
        cache_hit = True
        consumed_resolve_token = resolve_token
    collector_type = _collector_type_for_provider(provider)
    creator, creator_created = _get_or_create_creator_for_work(
        db,
        resolved,
        collector_type=collector_type,
        collector_version=_collector_version_for_provider(provider),
        creator_id=creator_id,
        group_name=group_name,
        tags=tags or [],
        monitor_interval_minutes=monitor_interval_minutes,
        captured_at=started_at,
    )
    before_post_count = db.scalar(
        select(func.count())
        .select_from(ContentPost)
        .where(
            ContentPost.creator_id == creator.id,
            ContentPost.platform_content_id == resolved.content.platform_content_id,
        )
    )
    new_posts, snapshot_results = sync_content_posts(
        db,
        creator,
        [resolved.content],
        captured_at=started_at,
        data_source=collector_type,
    )

    creator.baseline_content_ids = _merge_content_ids(
        [resolved.content.platform_content_id],
        creator.baseline_content_ids or [],
    )
    if creator.content_baseline_established_at is None:
        creator.content_baseline_established_at = started_at
    creator.last_collected_at = started_at
    creator.next_collect_at = started_at + timedelta(minutes=creator.monitor_interval_minutes)
    if creator.last_content_status in {"pending", "no_new_content", "baseline_created"}:
        creator.last_content_status = "metrics_refreshed"
    if creator.data_quality_status in {"pending", "mock", "partial"}:
        creator.data_quality_status = "verified"
    creator.last_collection_error = None

    post = db.scalar(
        select(ContentPost)
        .options(selectinload(ContentPost.creator))
        .where(
            ContentPost.creator_id == creator.id,
            ContentPost.platform_content_id == resolved.content.platform_content_id,
        )
    )
    run = CollectionRun(
        creator_id=creator.id,
        task_type="single_work_add",
        status="success",
        trigger_source="manual",
        collector_type=collector_type,
        started_at=started_at,
        finished_at=utc_now(),
        result_summary={
            "collector_type": collector_type,
            "data_provider": provider,
            "collection_scope": "single_work",
            "content_status": "success",
            "platform_content_id": resolved.content.platform_content_id,
            "creator_created": creator_created,
            "post_created": bool(new_posts) or not before_post_count,
            "content_snapshot_count": len(snapshot_results),
            "warnings": warnings,
            "resolve_cache_hit": cache_hit,
            "creator_profile_fetch_skipped": False,
            "content_list_fetch_skipped": True,
            **usage_summary,
        },
    )
    run.duration_ms = max(0, round((run.finished_at - run.started_at).total_seconds() * 1000))
    db.add(run)
    db.commit()
    if consumed_resolve_token:
        _consume_cached_resolved_content_link(consumed_resolve_token)
    db.refresh(creator)
    db.refresh(post)
    db.refresh(run)
    return LinkedContentResult(
        post=post,
        creator=creator,
        creator_created=creator_created,
        post_created=bool(new_posts) or not bool(before_post_count),
        run=run,
        warnings=warnings,
    )


def _resolve_cache_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )


def _resolve_cache_key(token: str) -> str:
    return f"{_RESOLVE_CACHE_PREFIX}:{token}"


def _cache_input_hash(platform: str, input_value: str, data_provider: str | None = None) -> str:
    provider = _normalize_single_work_provider(data_provider)
    normalized = f"{provider}:{platform}:{input_value.strip()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _remember_local_cache(token: str, expires_at: datetime, payload: str) -> None:
    now = utc_now()
    for key, (cached_expires_at, _value) in list(_LOCAL_RESOLVE_CACHE.items()):
        if cached_expires_at <= now:
            _LOCAL_RESOLVE_CACHE.pop(key, None)
    _LOCAL_RESOLVE_CACHE[token] = (expires_at, payload)


def _read_local_cache(token: str) -> str | None:
    cached = _LOCAL_RESOLVE_CACHE.get(token)
    if cached is None:
        return None
    expires_at, payload = cached
    if expires_at <= utc_now():
        _LOCAL_RESOLVE_CACHE.pop(token, None)
        return None
    return payload


def _consume_cached_resolved_content_link(token: str) -> None:
    _LOCAL_RESOLVE_CACHE.pop(token, None)
    try:
        client = _resolve_cache_client()
        client.delete(_resolve_cache_key(token))
        client.close()
    except RedisError:
        return


def _load_cached_resolved_content_link(
    *,
    platform: str,
    input_value: str,
    data_provider: str,
    resolve_token: str | None,
) -> tuple[TikHubResolvedWork, dict, list[str]] | None:
    if not resolve_token:
        return None
    payload_text = _read_local_cache(resolve_token)
    if payload_text is None:
        try:
            client = _resolve_cache_client()
            payload_text = client.get(_resolve_cache_key(resolve_token))
            client.close()
        except RedisError:
            payload_text = None
    if not payload_text:
        return None

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if payload.get("platform") != platform:
        return None
    provider = _normalize_single_work_provider(data_provider)
    if payload.get("data_provider", "tikhub") != provider:
        return None
    if payload.get("input_hash") != _cache_input_hash(platform, input_value, provider):
        return None
    return (
        _resolved_work_from_cache_payload(payload["resolved"]),
        payload.get("usage_summary") or {},
        list(payload.get("warnings") or []),
    )


def _resolved_work_to_cache_payload(resolved: TikHubResolvedWork) -> dict:
    return {
        "creator": {
            "platform_account_id": resolved.creator.platform_account_id,
            "platform_display_id": resolved.creator.platform_display_id,
            "nickname": resolved.creator.nickname,
            "profile_url": resolved.creator.profile_url,
            "avatar_url": resolved.creator.avatar_url,
            "bio": resolved.creator.bio,
            "verified_info": resolved.creator.verified_info,
            "location": resolved.creator.location,
            "follower_count": resolved.creator.follower_count,
            "following_count": resolved.creator.following_count,
            "total_like_count": resolved.creator.total_like_count,
            "content_count": resolved.creator.content_count,
        },
        "content": {
            "platform_content_id": resolved.content.platform_content_id,
            "title": resolved.content.title,
            "summary": resolved.content.summary,
            "content_type": resolved.content.content_type,
            "content_url": resolved.content.content_url,
            "cover_url": resolved.content.cover_url,
            "published_at": _datetime_to_cache_value(resolved.content.published_at),
            "like_count": resolved.content.like_count,
            "comment_count": resolved.content.comment_count,
            "collect_count": resolved.content.collect_count,
            "share_count": resolved.content.share_count,
            "metrics_status": resolved.content.metrics_status,
            "raw_data": resolved.content.raw_data,
        },
        "source_url": resolved.source_url,
        "raw_data": resolved.raw_data,
    }


def _resolved_work_from_cache_payload(payload: dict) -> TikHubResolvedWork:
    creator = payload["creator"]
    content = payload["content"]
    resolved_creator = TikHubResolvedCreator(
        platform_account_id=creator["platform_account_id"],
        platform_display_id=creator.get("platform_display_id"),
        nickname=creator["nickname"],
        profile_url=creator["profile_url"],
        avatar_url=creator.get("avatar_url"),
        bio=creator.get("bio"),
        verified_info=creator.get("verified_info"),
        location=creator.get("location"),
        follower_count=int(creator.get("follower_count") or 0),
        following_count=int(creator.get("following_count") or 0),
        total_like_count=int(creator.get("total_like_count") or 0),
        content_count=int(creator.get("content_count") or 0),
    )
    resolved_content = ContentProfile(
        platform_content_id=content["platform_content_id"],
        title=content["title"],
        summary=content.get("summary"),
        content_type=content.get("content_type") or "video",
        content_url=content["content_url"],
        cover_url=content.get("cover_url"),
        published_at=_datetime_from_cache_value(content.get("published_at")),
        like_count=int(content.get("like_count") or 0),
        comment_count=int(content.get("comment_count") or 0),
        collect_count=int(content.get("collect_count") or 0),
        share_count=int(content.get("share_count") or 0),
        metrics_status=content.get("metrics_status") or "success",
        raw_data=content.get("raw_data"),
    )
    return TikHubResolvedWork(
        creator=resolved_creator,
        content=resolved_content,
        source_url=payload["source_url"],
        raw_data=payload.get("raw_data") or {},
    )


def _datetime_to_cache_value(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _datetime_from_cache_value(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _normalize_single_work_provider(data_provider: str | None = None) -> str:
    provider = (data_provider or settings.douyin_single_work_provider or "tikhub").strip().lower()
    if provider != "tikhub":
        raise CollectorConfigurationError(f"当前只支持 TikHub 抖音作品数据源，不再调用旧平台: {provider}")
    return provider


def _collector_type_for_provider(provider: str) -> str:
    _normalize_single_work_provider(provider)
    return "tikhub_douyin"


def _collector_version_for_provider(provider: str) -> str:
    _normalize_single_work_provider(provider)
    return "tikhub-douyin-single-work-v1"


def _tikhub_spent_today_usd(db: Session, started_at: datetime) -> float:
    day_start = started_at.replace(hour=0, minute=0, second=0, microsecond=0)
    query = select(CollectionRun.result_summary).where(
        CollectionRun.collector_type == "tikhub_douyin",
        CollectionRun.started_at >= day_start,
    )
    total = 0.0
    for summary in db.scalars(query).all():
        if not isinstance(summary, dict):
            continue
        try:
            total += float(summary.get("tikhub_estimated_cost_usd") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _get_or_create_creator_for_work(
    db: Session,
    resolved: TikHubResolvedWork,
    *,
    collector_type: str,
    collector_version: str,
    creator_id: int | None,
    group_name: str | None,
    tags: list[str],
    monitor_interval_minutes: int,
    captured_at: datetime,
) -> tuple[CreatorAccount, bool]:
    if creator_id is not None:
        creator = db.get(CreatorAccount, creator_id)
        if creator is None:
            raise CollectorConfigurationError("选择的作者不存在")
        if creator.platform != "douyin":
            raise CollectorConfigurationError("抖音作品只能绑定抖音作者")
        return creator, False

    creator = _find_creator_for_resolved_work(db, resolved)
    if creator is not None:
        _merge_creator_profile_from_work(creator, resolved, collector_type=collector_type)
        return creator, False

    creator_info = resolved.creator
    creator = CreatorAccount(
        platform="douyin",
        platform_account_id=creator_info.platform_account_id,
        platform_display_id=creator_info.platform_display_id,
        nickname=creator_info.nickname,
        profile_url=creator_info.profile_url,
        avatar_url=creator_info.avatar_url,
        bio=creator_info.bio,
        verified_info=creator_info.verified_info,
        location=creator_info.location,
        group_name=group_name or "单作品监控",
        tags=tags or ["单作品"],
        priority="normal",
        monitor_interval_minutes=monitor_interval_minutes,
        monitor_scope="single_content",
        monitoring_status="active",
        collector_type=collector_type,
        collector_version=collector_version,
        data_quality_status="verified",
        last_content_status="metrics_refreshed",
        follower_count=creator_info.follower_count,
        following_count=creator_info.following_count,
        total_like_count=creator_info.total_like_count,
        content_count=creator_info.content_count,
        last_collected_at=captured_at,
        next_collect_at=captured_at + timedelta(minutes=monitor_interval_minutes),
        baseline_content_ids=[resolved.content.platform_content_id],
        content_baseline_established_at=captured_at,
    )
    db.add(creator)
    db.flush()
    db.add(
        CreatorSnapshot(
            creator_id=creator.id,
            follower_count=creator.follower_count,
            following_count=creator.following_count,
            total_like_count=creator.total_like_count,
            content_count=creator.content_count,
            collector_type=creator.collector_type,
            data_quality_status=creator.data_quality_status,
            captured_at=captured_at,
        )
    )
    return creator, True


def _find_creator_for_resolved_work(
    db: Session,
    resolved: TikHubResolvedWork,
) -> CreatorAccount | None:
    creator_info = resolved.creator
    creator = db.scalar(
        select(CreatorAccount).where(
            CreatorAccount.platform == "douyin",
            CreatorAccount.platform_account_id == creator_info.platform_account_id,
        )
    )
    if creator is not None:
        return creator
    if not creator_info.platform_display_id:
        return None
    return db.scalar(
        select(CreatorAccount).where(
            CreatorAccount.platform == "douyin",
            CreatorAccount.platform_display_id == creator_info.platform_display_id,
        )
    )


def _merge_creator_profile_from_work(
    creator: CreatorAccount,
    resolved: TikHubResolvedWork,
    *,
    collector_type: str,
) -> None:
    creator_info = resolved.creator
    creator.platform_display_id = creator.platform_display_id or creator_info.platform_display_id
    creator.nickname = creator_info.nickname or creator.nickname
    creator.profile_url = creator_info.profile_url or creator.profile_url
    creator.avatar_url = creator_info.avatar_url or creator.avatar_url
    creator.bio = creator_info.bio or creator.bio
    creator.verified_info = creator_info.verified_info or creator.verified_info
    creator.location = creator_info.location or creator.location
    creator.follower_count = max(creator.follower_count, creator_info.follower_count)
    creator.following_count = max(creator.following_count, creator_info.following_count)
    creator.total_like_count = max(creator.total_like_count, creator_info.total_like_count)
    creator.content_count = max(creator.content_count, creator_info.content_count)
    if creator.monitor_scope == "single_content" or creator.collector_type == "mock":
        creator.collector_type = collector_type


def _merge_content_ids(*groups: list[str] | tuple[str, ...] | None) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group or []:
            content_id = str(value).strip()
            if not content_id or content_id in seen:
                continue
            merged.append(content_id)
            seen.add(content_id)
            if len(merged) >= 500:
                return merged
    return merged


def sync_content_posts(
    db: Session,
    creator: CreatorAccount,
    profiles: list[ContentProfile],
    *,
    captured_at: datetime,
    data_source: str | None = None,
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
                data_source=data_source or creator.collector_type,
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
            post.data_source = data_source or creator.collector_type
            post.metrics_status = profile.metrics_status
            post.raw_data_json = profile.raw_data
            if profile.published_at is not None:
                post.published_at = profile.published_at

        if profile.metrics_status not in {"success", "partial"}:
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
    sort_time = func.coalesce(ContentPost.published_at, ContentPost.first_discovered_at)
    query = (
        select(ContentPost)
        .join(CreatorAccount, ContentPost.creator_id == CreatorAccount.id)
        .options(selectinload(ContentPost.creator))
        .where(*filters)
        .order_by(ContentPost.first_discovered_at.desc(), sort_time.desc(), ContentPost.id.desc())
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
