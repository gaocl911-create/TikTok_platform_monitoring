from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.collection_run import CollectionRun


def get_collection_run(db: Session, run_id: int) -> CollectionRun | None:
    query = (
        select(CollectionRun)
        .options(selectinload(CollectionRun.creator))
        .where(CollectionRun.id == run_id)
    )
    return db.scalar(query)


def list_collection_runs(
    db: Session,
    *,
    page: int,
    page_size: int,
    creator_id: int | None = None,
    status: str | None = None,
    collector_type: str | None = None,
) -> tuple[list[CollectionRun], int]:
    filters = []
    if creator_id:
        filters.append(CollectionRun.creator_id == creator_id)
    if status:
        filters.append(CollectionRun.status == status)
    if collector_type:
        filters.append(CollectionRun.collector_type == collector_type)

    total = db.scalar(select(func.count(CollectionRun.id)).where(*filters)) or 0
    query = (
        select(CollectionRun)
        .options(selectinload(CollectionRun.creator))
        .where(*filters)
        .order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(query).all()), total
