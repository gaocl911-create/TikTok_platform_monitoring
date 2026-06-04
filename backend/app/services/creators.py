from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors import CollectorConfigurationError, get_collector
from app.models.base import utc_now
from app.models.collection_run import CollectionRun
from app.models.creator import CreatorAccount
from app.models.creator_snapshot import CreatorSnapshot
from app.schemas.creator import CreatorCreate, CreatorUpdate
from app.services.alerts import dispatch_alert_notifications, evaluate_content_alerts
from app.services.posts import sync_content_posts


class CreatorAlreadyExistsError(Exception):
    pass


def create_creator(db: Session, payload: CreatorCreate) -> CreatorAccount:
    data_quality_status = "mock" if payload.collector_type == "mock" else "pending"
    creator = CreatorAccount(
        **payload.model_dump(),
        monitoring_status="active",
        data_quality_status=data_quality_status,
        next_collect_at=utc_now(),
    )
    db.add(creator)
    try:
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
    if collector_type == "douyin_public_web" and creator.platform != "douyin":
        raise CollectorConfigurationError("抖音公开主页采集器只能用于抖音账号")

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


def collect_creator(db: Session, creator: CreatorAccount):
    started_at = utc_now()
    run = CollectionRun(
        creator_id=creator.id,
        status="running",
        started_at=started_at,
    )
    db.add(run)
    db.flush()

    before = {
        "follower_count": creator.follower_count,
        "total_like_count": creator.total_like_count,
        "content_count": creator.content_count,
    }

    collector = None
    try:
        collector = get_collector(creator)
        profile = collector.fetch_creator_profile(creator)
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

        content_profiles = collector.fetch_content_posts(creator)
        content_status = collector.content_status
        warnings = list(collector.warnings)
        new_posts, content_snapshot_results = sync_content_posts(
            db,
            creator,
            content_profiles,
            captured_at=started_at,
        )
        alerts = evaluate_content_alerts(db, creator, new_posts, content_snapshot_results)

        if collector.collector_type == "mock":
            data_quality_status = "mock"
        elif content_status == "success":
            data_quality_status = "verified"
        else:
            data_quality_status = "partial"

        creator.collector_version = collector.version
        creator.data_quality_status = data_quality_status
        creator.last_content_status = content_status
        creator.last_collection_error = "；".join(warnings) or None
        snapshot.data_quality_status = data_quality_status

        run.status = "partial" if data_quality_status == "partial" else "success"
        run.finished_at = utc_now()
        run.result_summary = {
            "collector_type": collector.collector_type,
            "collector_version": collector.version,
            "data_quality_status": data_quality_status,
            "content_status": content_status,
            "warnings": warnings,
            "follower_delta": creator.follower_count - before["follower_count"],
            "like_delta": creator.total_like_count - before["total_like_count"],
            "content_delta": creator.content_count - before["content_count"],
            "new_content_count": len(new_posts),
            "content_snapshot_count": len(content_snapshot_results),
            "alert_count": len(alerts),
        }
        db.commit()
        dispatch_alert_notifications(db, alerts)
        db.refresh(creator)
        db.refresh(snapshot)
        db.refresh(run)
        return creator, snapshot, run
    except Exception as exc:
        db.rollback()
        creator = db.get(CreatorAccount, creator.id)
        if creator is not None:
            creator.consecutive_failures += 1
            creator.next_collect_at = utc_now() + timedelta(minutes=15)
            creator.collector_version = getattr(collector, "version", None)
            creator.data_quality_status = "failed"
            creator.last_content_status = "failed"
            creator.last_collection_error = str(exc)
        failed_run = CollectionRun(
            creator_id=run.creator_id,
            status="failed",
            started_at=started_at,
            finished_at=utc_now(),
            error_message=str(exc),
            result_summary={
                "collector_type": creator.collector_type if creator is not None else "unknown",
                "data_quality_status": "failed",
                "content_status": "failed",
            },
        )
        db.add(failed_run)
        db.commit()
        raise


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
