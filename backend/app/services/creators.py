from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors import MockCollector
from app.models.base import utc_now
from app.models.collection_run import CollectionRun
from app.models.creator import CreatorAccount
from app.models.creator_snapshot import CreatorSnapshot
from app.schemas.creator import CreatorCreate, CreatorUpdate


class CreatorAlreadyExistsError(Exception):
    pass


def create_creator(db: Session, payload: CreatorCreate) -> CreatorAccount:
    creator = CreatorAccount(
        **payload.model_dump(),
        monitoring_status="active",
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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(creator, field, value)

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

    try:
        profile = MockCollector().fetch_creator_profile(creator)
        creator.nickname = profile.nickname
        creator.avatar_url = profile.avatar_url
        creator.bio = profile.bio
        creator.verified_info = profile.verified_info
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
            captured_at=started_at,
        )
        db.add(snapshot)

        run.status = "success"
        run.finished_at = utc_now()
        run.result_summary = {
            "follower_delta": creator.follower_count - before["follower_count"],
            "like_delta": creator.total_like_count - before["total_like_count"],
            "content_delta": creator.content_count - before["content_count"],
        }
        db.commit()
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
        failed_run = CollectionRun(
            creator_id=run.creator_id,
            status="failed",
            started_at=started_at,
            finished_at=utc_now(),
            error_message=str(exc),
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
