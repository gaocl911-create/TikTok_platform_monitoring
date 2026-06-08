from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors import CollectorConfigurationError, TikOmniDouyinCollector, get_collector
from app.models.base import utc_now
from app.models.collection_run import CollectionRun
from app.models.content_post import ContentPost
from app.models.creator import CreatorAccount
from app.models.creator_snapshot import CreatorSnapshot
from app.schemas.creator import CreatorCreate, CreatorUpdate
from app.services.alerts import (
    dispatch_alert_notifications,
    evaluate_collection_failure_alert,
    evaluate_content_alerts,
)
from app.services.posts import sync_content_posts
from app.utils.profile_urls import normalize_profile_url


class CreatorAlreadyExistsError(Exception):
    pass


MAX_BASELINE_CONTENT_IDS = 500


@dataclass(slots=True)
class _TrackedContentContext:
    platform_content_id: str
    title: str
    summary: str | None
    content_type: str
    content_url: str
    cover_url: str | None
    published_at: datetime | None
    latest_like_count: int
    latest_comment_count: int
    latest_collect_count: int
    latest_share_count: int


@dataclass(slots=True)
class _CreatorCollectionContext:
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
    collector_type: str
    follower_count: int
    following_count: int
    total_like_count: int
    content_count: int
    monitor_interval_minutes: int
    monitor_scope: str
    baseline_content_ids: list[str]
    known_content_ids: list[str]
    tracked_content_posts: list[_TrackedContentContext]
    tikomni_spent_today_cny: float = 0


@dataclass(slots=True)
class ResolvedCreatorProfile:
    platform: str
    platform_account_id: str
    platform_display_id: str | None
    nickname: str
    profile_url: str
    avatar_url: str | None
    bio: str | None
    verified_info: str | None
    location: str | None
    follower_count: int
    following_count: int
    total_like_count: int
    content_count: int
    collector_type: str
    sec_user_id: str | None
    warnings: list[str]


def _collection_context(
    creator: CreatorAccount,
    *,
    known_content_ids: list[str] | None = None,
    tracked_content_posts: list[_TrackedContentContext] | None = None,
) -> _CreatorCollectionContext:
    return _CreatorCollectionContext(
        id=creator.id,
        platform=creator.platform,
        platform_account_id=creator.platform_account_id,
        platform_display_id=creator.platform_display_id,
        nickname=creator.nickname,
        profile_url=creator.profile_url,
        avatar_url=creator.avatar_url,
        bio=creator.bio,
        verified_info=creator.verified_info,
        location=creator.location,
        collector_type=creator.collector_type,
        follower_count=creator.follower_count,
        following_count=creator.following_count,
        total_like_count=creator.total_like_count,
        content_count=creator.content_count,
        monitor_interval_minutes=creator.monitor_interval_minutes,
        monitor_scope=creator.monitor_scope,
        baseline_content_ids=list(creator.baseline_content_ids or []),
        known_content_ids=known_content_ids or [],
        tracked_content_posts=tracked_content_posts or [],
    )


def _tikomni_spent_today_cny(db: Session, started_at) -> float:
    day_start = started_at.replace(hour=0, minute=0, second=0, microsecond=0)
    query = select(CollectionRun.result_summary).where(
        CollectionRun.collector_type == "tikomni_douyin",
        CollectionRun.started_at >= day_start,
    )
    total = 0.0
    for summary in db.scalars(query).all():
        if not isinstance(summary, dict):
            continue
        try:
            total += float(summary.get("tikomni_estimated_cost_cny") or 0)
        except (TypeError, ValueError):
            continue
    return total


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
            if len(merged) >= MAX_BASELINE_CONTENT_IDS:
                return merged
    return merged


def _known_content_ids(db: Session, creator: CreatorAccount) -> list[str]:
    existing_ids = list(
        db.scalars(
            select(ContentPost.platform_content_id).where(ContentPost.creator_id == creator.id)
        ).all()
    )
    return _merge_content_ids(existing_ids, creator.baseline_content_ids or [])


def _tracked_content_contexts(db: Session, creator: CreatorAccount) -> list[_TrackedContentContext]:
    query = (
        select(ContentPost)
        .where(ContentPost.creator_id == creator.id, ContentPost.status == "active")
        .order_by(ContentPost.first_discovered_at.desc(), ContentPost.id.desc())
    )
    return [
        _TrackedContentContext(
            platform_content_id=post.platform_content_id,
            title=post.title,
            summary=post.summary,
            content_type=post.content_type,
            content_url=post.content_url,
            cover_url=post.cover_url,
            published_at=post.published_at,
            latest_like_count=post.latest_like_count,
            latest_comment_count=post.latest_comment_count,
            latest_collect_count=post.latest_collect_count,
            latest_share_count=post.latest_share_count,
        )
        for post in db.scalars(query).all()
    ]


def _contains_http_url(value: str) -> bool:
    return "http://" in value.lower() or "https://" in value.lower()


def _profile_url_from_input(input_value: str) -> tuple[str, str, bool]:
    normalized_input = input_value.strip()
    if not normalized_input:
        raise CollectorConfigurationError("Profile input is required")
    if _contains_http_url(normalized_input):
        profile_url = normalize_profile_url(normalized_input)
        return profile_url, profile_url, True
    profile_url = f"https://www.douyin.com/user/{normalized_input}"
    return profile_url, normalized_input, False


def resolve_creator_profile(db: Session, *, platform: str, input_value: str) -> ResolvedCreatorProfile:
    if platform != "douyin":
        raise CollectorConfigurationError("Xiaohongshu profile resolving is not connected yet")

    started_at = utc_now()
    profile_url, platform_id_candidate, input_was_url = _profile_url_from_input(input_value)
    context = SimpleNamespace(
        id=0,
        platform="douyin",
        platform_account_id=platform_id_candidate,
        platform_display_id=None,
        nickname=platform_id_candidate,
        profile_url=profile_url,
        avatar_url=None,
        bio=None,
        verified_info=None,
        location=None,
        collector_type="tikomni_douyin",
        follower_count=0,
        following_count=0,
        total_like_count=0,
        content_count=0,
        monitor_interval_minutes=30,
        monitor_scope="creator_collection",
        baseline_content_ids=[],
        known_content_ids=[],
        tracked_content_posts=[],
        tikomni_spent_today_cny=_tikomni_spent_today_cny(db, started_at),
    )
    collector = TikOmniDouyinCollector(spent_today_cny=context.tikomni_spent_today_cny)
    profile = collector.fetch_creator_profile(context)
    sec_user_id = getattr(collector, "_sec_user_id", None)
    public_account_id = getattr(collector, "_public_account_id", None)
    resolved_profile_url = (
        f"https://www.douyin.com/user/{sec_user_id}" if sec_user_id else profile_url
    )
    platform_account_id = platform_id_candidate if not input_was_url else (sec_user_id or profile_url)
    if sec_user_id:
        platform_account_id = sec_user_id
    platform_display_id = public_account_id or (platform_id_candidate if not input_was_url else None)

    return ResolvedCreatorProfile(
        platform="douyin",
        platform_account_id=platform_account_id[:128],
        platform_display_id=platform_display_id[:128] if platform_display_id else None,
        nickname=profile.nickname,
        profile_url=resolved_profile_url,
        avatar_url=profile.avatar_url,
        bio=profile.bio,
        verified_info=profile.verified_info,
        location=profile.location,
        follower_count=profile.follower_count,
        following_count=profile.following_count,
        total_like_count=profile.total_like_count,
        content_count=profile.content_count,
        collector_type=collector.collector_type,
        sec_user_id=sec_user_id,
        warnings=list(collector.warnings),
    )


def create_creator(db: Session, payload: CreatorCreate) -> CreatorAccount:
    now = utc_now()
    data_quality_status = (
        "mock"
        if payload.collector_type == "mock"
        else "partial"
        if payload.profile_resolved
        else "pending"
    )
    creator_payload = payload.model_dump(exclude={"profile_resolved"})
    creator = CreatorAccount(
        **creator_payload,
        monitoring_status="active",
        data_quality_status=data_quality_status,
        last_content_status="pending",
        last_collected_at=now if payload.profile_resolved else None,
        next_collect_at=(
            now + timedelta(minutes=payload.monitor_interval_minutes)
            if payload.profile_resolved
            else now + timedelta(minutes=1)
        ),
    )
    db.add(creator)
    try:
        db.flush()
        if payload.profile_resolved:
            db.add(
                CreatorSnapshot(
                    creator_id=creator.id,
                    follower_count=creator.follower_count,
                    following_count=creator.following_count,
                    total_like_count=creator.total_like_count,
                    content_count=creator.content_count,
                    collector_type=creator.collector_type,
                    data_quality_status=data_quality_status,
                    captured_at=now,
                )
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CreatorAlreadyExistsError from exc
    db.refresh(creator)
    return creator


def get_creator(db: Session, creator_id: int) -> CreatorAccount | None:
    return db.get(CreatorAccount, creator_id)


def list_creators(
    db: Session,
    *,
    page: int,
    page_size: int,
    platform: str | None = None,
    monitoring_status: str | None = None,
    search: str | None = None,
) -> tuple[list[CreatorAccount], int]:
    filters = []
    if platform:
        filters.append(CreatorAccount.platform == platform)
    if monitoring_status:
        filters.append(CreatorAccount.monitoring_status == monitoring_status)
    if search:
        keyword = f"%{search.strip()}%"
        filters.append(
            or_(
                CreatorAccount.nickname.like(keyword),
                CreatorAccount.platform_account_id.like(keyword),
                CreatorAccount.platform_display_id.like(keyword),
                CreatorAccount.group_name.like(keyword),
            )
        )

    count_query = select(func.count(CreatorAccount.id)).where(*filters)
    total = db.scalar(count_query) or 0
    query = (
        select(CreatorAccount)
        .where(*filters)
        .order_by(CreatorAccount.priority, CreatorAccount.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(query).all()), total


def update_creator(db: Session, creator: CreatorAccount, payload: CreatorUpdate) -> CreatorAccount:
    updates = payload.model_dump(exclude_unset=True)
    collector_type = updates.get("collector_type")
    previous_collector_type = creator.collector_type
    if collector_type in {"douyin_public_web", "tikomni_douyin"} and creator.platform != "douyin":
        raise CollectorConfigurationError("抖音真实采集器只能用于抖音账号")

    for field, value in updates.items():
        setattr(creator, field, value)

    if collector_type is not None and collector_type != previous_collector_type:
        creator.collector_version = None
        creator.data_quality_status = "mock" if collector_type == "mock" else "pending"
        creator.last_content_status = "pending"
        creator.last_collection_error = None
        creator.follower_count = 0
        creator.following_count = 0
        creator.total_like_count = 0
        creator.content_count = 0
        creator.last_collected_at = None
        creator.consecutive_failures = 0
        creator.next_collect_at = utc_now()
        if previous_collector_type == "mock" and collector_type != "mock":
            for post in list(creator.posts):
                if post.data_source == "mock":
                    db.delete(post)
            for alert in list(creator.alerts):
                db.delete(alert)

    if creator.monitoring_status == "active" and creator.next_collect_at is None:
        creator.next_collect_at = utc_now()
    db.commit()
    db.refresh(creator)
    return creator


def delete_creator(db: Session, creator: CreatorAccount) -> None:
    db.delete(creator)
    db.commit()


def _duration_ms(started_at, finished_at) -> int:
    return max(0, round((finished_at - started_at).total_seconds() * 1000))


def collect_creator(
    db: Session,
    creator: CreatorAccount,
    *,
    trigger_source: str = "manual",
    attempt: int = 1,
    include_content: bool = True,
):
    started_at = utc_now()
    creator_id = creator.id
    context = _collection_context(
        creator,
        known_content_ids=_known_content_ids(db, creator),
        tracked_content_posts=_tracked_content_contexts(db, creator),
    )
    if context.collector_type == "tikomni_douyin":
        context = replace(
            context,
            tikomni_spent_today_cny=_tikomni_spent_today_cny(db, started_at),
        )
    run = CollectionRun(
        creator_id=creator_id,
        status="running",
        trigger_source=trigger_source,
        attempt=attempt,
        collector_type=creator.collector_type,
        started_at=started_at,
    )
    db.add(run)
    db.flush()
    run_id = run.id
    db.commit()

    before = {
        "follower_count": context.follower_count,
        "total_like_count": context.total_like_count,
        "content_count": context.content_count,
    }

    collector = None
    try:
        collector = get_collector(context)
        profile = collector.fetch_creator_profile(context)
        resolved_display_id = getattr(collector, "_public_account_id", None)
        collected_context = replace(
            context,
            platform_display_id=resolved_display_id or context.platform_display_id,
            nickname=profile.nickname,
            avatar_url=profile.avatar_url or context.avatar_url,
            bio=profile.bio,
            verified_info=profile.verified_info or context.verified_info,
            location=profile.location,
            follower_count=profile.follower_count,
            following_count=profile.following_count,
            total_like_count=profile.total_like_count,
            content_count=profile.content_count,
        )
        if include_content:
            content_profiles = collector.fetch_content_posts(collected_context)
            content_status = collector.content_status
        else:
            content_profiles = []
            content_status = "pending"
        warnings = list(collector.warnings)

        creator = db.get(CreatorAccount, creator_id)
        run = db.get(CollectionRun, run_id)
        if creator is None or run is None:
            raise RuntimeError("采集账号或运行记录不存在")

        run.collector_type = collector.collector_type
        creator.platform_display_id = resolved_display_id or creator.platform_display_id
        creator.nickname = profile.nickname
        creator.avatar_url = profile.avatar_url or creator.avatar_url
        creator.bio = profile.bio
        creator.verified_info = profile.verified_info or creator.verified_info
        creator.location = profile.location
        creator.follower_count = profile.follower_count
        creator.following_count = profile.following_count
        creator.total_like_count = profile.total_like_count
        creator.content_count = profile.content_count
        creator.last_collected_at = started_at
        creator.next_collect_at = started_at + timedelta(minutes=creator.monitor_interval_minutes)
        creator.consecutive_failures = 0

        snapshot = CreatorSnapshot(
            creator_id=creator.id,
            follower_count=creator.follower_count,
            following_count=creator.following_count,
            total_like_count=creator.total_like_count,
            content_count=creator.content_count,
            collector_type=collector.collector_type,
            data_quality_status="pending",
            captured_at=started_at,
        )
        db.add(snapshot)

        new_posts, content_snapshot_results = sync_content_posts(
            db,
            creator,
            content_profiles,
            captured_at=started_at,
        )
        last_seen_content_ids = list(getattr(collector, "last_seen_content_ids", []) or [])
        new_content_ids = list(getattr(collector, "new_content_ids", []) or [])
        refreshed_content_ids = list(getattr(collector, "refreshed_content_ids", []) or [])
        baseline_created = bool(getattr(collector, "baseline_created", False))
        if last_seen_content_ids:
            creator.baseline_content_ids = _merge_content_ids(
                last_seen_content_ids,
                creator.baseline_content_ids or [],
            )
            if creator.content_baseline_established_at is None:
                creator.content_baseline_established_at = started_at
        alerts = (
            evaluate_content_alerts(db, creator, new_posts, content_snapshot_results)
            if include_content
            else []
        )

        if collector.collector_type == "mock":
            data_quality_status = "mock"
        elif not include_content:
            data_quality_status = "partial"
        elif content_status in {
            "success",
            "no_new_content",
            "baseline_created",
            "metrics_refreshed",
        }:
            data_quality_status = "verified"
        else:
            data_quality_status = "partial"

        creator.collector_version = collector.version
        creator.data_quality_status = data_quality_status
        creator.last_content_status = content_status
        stored_warnings = (
            []
            if content_status in {"baseline_created", "no_new_content"}
            else warnings
        )
        creator.last_collection_error = "；".join(stored_warnings) or None
        snapshot.data_quality_status = data_quality_status

        run.status = (
            "success"
            if not include_content
            else "partial"
            if data_quality_status == "partial"
            else "success"
        )
        run.finished_at = utc_now()
        run.duration_ms = _duration_ms(started_at, run.finished_at)
        result_summary = {
            "collector_type": collector.collector_type,
            "collector_version": collector.version,
            "collection_scope": "full" if include_content else "profile",
            "data_quality_status": data_quality_status,
            "content_status": content_status,
            "warnings": warnings,
            "follower_delta": creator.follower_count - before["follower_count"],
            "like_delta": creator.total_like_count - before["total_like_count"],
            "content_delta": creator.content_count - before["content_count"],
            "new_content_count": len(new_posts),
            "content_snapshot_count": len(content_snapshot_results),
            "alert_count": len(alerts),
            "content_list_seen_count": len(last_seen_content_ids),
            "new_content_candidate_count": len(new_content_ids),
            "refreshed_content_count": len(refreshed_content_ids),
            "content_baseline_created": baseline_created,
            "content_baseline_size": len(creator.baseline_content_ids or []),
            "expensive_content_fetch_skipped": include_content
            and content_status in {"baseline_created", "no_new_content"},
        }
        if hasattr(collector, "usage_summary"):
            result_summary.update(collector.usage_summary())
        run.result_summary = result_summary
        db.commit()
        dispatch_alert_notifications(db, alerts)
        db.refresh(creator)
        db.refresh(snapshot)
        db.refresh(run)
        return creator, snapshot, run
    except Exception as exc:
        db.rollback()
        creator = db.get(CreatorAccount, creator_id)
        run = db.get(CollectionRun, run_id)
        finished_at = utc_now()
        error_type = type(exc).__name__
        if creator is not None:
            creator.consecutive_failures += 1
            creator.next_collect_at = utc_now() + timedelta(minutes=15)
            creator.collector_version = getattr(collector, "version", None)
            creator.data_quality_status = "failed"
            creator.last_content_status = "failed"
            creator.last_collection_error = str(exc)
        if run is None:
            run = CollectionRun(
                creator_id=creator_id,
                trigger_source=trigger_source,
                attempt=attempt,
                started_at=started_at,
            )
            db.add(run)
        run.status = "failed"
        run.collector_type = (
            creator.collector_type if creator is not None else context.collector_type
        )
        run.error_type = error_type
        run.duration_ms = _duration_ms(started_at, finished_at)
        run.finished_at = finished_at
        run.error_message = str(exc)
        result_summary = {
            "collector_type": run.collector_type or "unknown",
            "data_quality_status": "failed",
            "content_status": "failed",
        }
        if collector is not None and hasattr(collector, "usage_summary"):
            result_summary.update(collector.usage_summary())
        run.result_summary = result_summary
        db.flush()
        alerts = (
            evaluate_collection_failure_alert(
                db,
                creator,
                run_id=run.id,
                error_type=error_type,
                error_message=str(exc),
            )
            if creator is not None
            else []
        )
        db.commit()
        dispatch_alert_notifications(db, alerts)
        raise


def record_skipped_collection_run(
    db: Session,
    creator: CreatorAccount,
    *,
    trigger_source: str,
    reason: str,
    attempt: int = 1,
) -> CollectionRun:
    now = utc_now()
    run = CollectionRun(
        creator_id=creator.id,
        status="skipped",
        trigger_source=trigger_source,
        attempt=attempt,
        collector_type=creator.collector_type,
        started_at=now,
        finished_at=now,
        duration_ms=0,
        error_type="CollectionAlreadyRunning",
        error_message=reason,
        result_summary={
            "collector_type": creator.collector_type,
            "data_quality_status": creator.data_quality_status,
            "content_status": creator.last_content_status,
            "reason": reason,
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def list_snapshots(
    db: Session,
    creator_id: int,
    *,
    limit: int = 100,
) -> list[CreatorSnapshot]:
    query = (
        select(CreatorSnapshot)
        .where(CreatorSnapshot.creator_id == creator_id)
        .order_by(CreatorSnapshot.captured_at.desc())
        .limit(limit)
    )
    snapshots = list(db.scalars(query).all())
    snapshots.reverse()
    return snapshots


def list_due_creator_ids(db: Session, *, limit: int = 100) -> list[int]:
    now = utc_now()
    query = (
        select(CreatorAccount.id)
        .where(
            CreatorAccount.monitoring_status == "active",
            CreatorAccount.next_collect_at <= now,
        )
        .order_by(CreatorAccount.next_collect_at.asc())
        .limit(limit)
    )
    return list(db.scalars(query).all())
