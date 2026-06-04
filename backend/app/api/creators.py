from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.creator import (
    CollectionResult,
    CreatorCreate,
    CreatorListResponse,
    CreatorRead,
    CreatorSnapshotRead,
    CreatorUpdate,
)
from app.services.creators import (
    CreatorAlreadyExistsError,
    collect_creator,
    create_creator,
    delete_creator,
    get_creator,
    list_creators,
    list_snapshots,
    update_creator,
)

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
    creator, _, _ = collect_creator(db, creator)
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
    return update_creator(db, require_creator(db, creator_id), payload)


@router.delete("/{creator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_creator_endpoint(creator_id: int, db: DbSession) -> None:
    delete_creator(db, require_creator(db, creator_id))


@router.post("/{creator_id}/collect", response_model=CollectionResult)
def collect_creator_endpoint(creator_id: int, db: DbSession):
    creator, snapshot, run = collect_creator(db, require_creator(db, creator_id))
    return CollectionResult(creator=creator, snapshot=snapshot, run=run)


@router.get("/{creator_id}/snapshots", response_model=list[CreatorSnapshotRead])
def list_creator_snapshots_endpoint(
    creator_id: int,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
):
    require_creator(db, creator_id)
    return list_snapshots(db, creator_id, limit=limit)
