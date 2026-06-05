from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.collectors import CollectorError, CollectorTransientError
from app.core.config import settings
from app.core.database import get_db
from app.schemas.creator import (
    CollectionResult,
    CollectionRetryQueued,
    CreatorCreate,
    CreatorListResponse,
    CreatorRead,
    CreatorSnapshotRead,
    CreatorUpdate,
)
from app.services.collection_locks import acquire_creator_collection_lock
from app.services.creators import (
    CreatorAlreadyExistsError,
    collect_creator,
    create_creator,
    delete_creator,
    get_creator,
    list_creators,
    list_snapshots,
    record_skipped_collection_run,
    update_creator,
)
from app.tasks.collection import collect_creator_task

router = APIRouter(prefix="/creators", tags=["creators"])
DbSession = Annotated[Session, Depends(get_db)]


def require_creator(db: Session, creator_id: int):
    creator = get_creator(db, creator_id)
    if creator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="监控账号不存在")
    return creator


@router.post("", response_model=CreatorRead, status_code=status.HTTP_201_CREATED)
def create_creator_endpoint(payload: CreatorCreate, db: DbSession):
    try:
        creator = create_creator(db, payload)
    except CreatorAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该平台账号已经处于监控列表中",
        ) from exc
    try:
        creator, _, _ = collect_creator(db, creator, trigger_source="initial")
    except CollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"账号已添加，但首次真实采集失败：{exc}",
        ) from exc
    return creator


@router.get("", response_model=CreatorListResponse)
def list_creators_endpoint(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    platform: str | None = None,
    monitoring_status: str | None = None,
    search: str | None = None,
):
    items, total = list_creators(
        db,
        page=page,
        page_size=page_size,
        platform=platform,
        monitoring_status=monitoring_status,
        search=search,
    )
    return CreatorListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{creator_id}", response_model=CreatorRead)
def get_creator_endpoint(creator_id: int, db: DbSession):
    return require_creator(db, creator_id)


@router.patch("/{creator_id}", response_model=CreatorRead)
def update_creator_endpoint(creator_id: int, payload: CreatorUpdate, db: DbSession):
    try:
        return update_creator(db, require_creator(db, creator_id), payload)
    except CollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete("/{creator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_creator_endpoint(creator_id: int, db: DbSession) -> None:
    delete_creator(db, require_creator(db, creator_id))


@router.post(
    "/{creator_id}/collect",
    response_model=CollectionResult | CollectionRetryQueued,
)
def collect_creator_endpoint(creator_id: int, db: DbSession, response: Response):
    creator = require_creator(db, creator_id)
    try:
        lock = acquire_creator_collection_lock(creator_id)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis 暂不可用，无法启动手动采集",
        ) from exc

    if lock is None:
        record_skipped_collection_run(
            db,
            creator,
            trigger_source="manual",
            reason="同一账号已有采集任务正在执行",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该账号已有采集任务正在执行，请稍后重试",
        )

    try:
        creator, snapshot, run = collect_creator(
            db,
            creator,
            trigger_source="manual",
        )
    except CollectorTransientError as exc:
        try:
            retry_task = collect_creator_task.apply_async(
                args=[creator_id, "manual"],
                countdown=settings.collection_retry_base_delay_seconds,
            )
        except Exception as queue_exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="首次采集失败，且自动重试任务无法加入队列",
            ) from queue_exc
        response.status_code = status.HTTP_202_ACCEPTED
        return CollectionRetryQueued(
            creator_id=creator_id,
            task_id=retry_task.id,
            status="queued",
            retry_after_seconds=settings.collection_retry_base_delay_seconds,
            message=f"首次采集失败，已加入自动重试队列：{exc}",
        )
    except CollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"真实采集失败：{exc}",
        ) from exc
    finally:
        lock.release()
    return CollectionResult(creator=creator, snapshot=snapshot, run=run)


@router.get("/{creator_id}/snapshots", response_model=list[CreatorSnapshotRead])
def list_creator_snapshots_endpoint(
    creator_id: int,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
):
    require_creator(db, creator_id)
    return list_snapshots(db, creator_id, limit=limit)
