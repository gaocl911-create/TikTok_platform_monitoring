from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.creator import CollectionRunListResponse, CollectionRunRead
from app.services.runs import get_collection_run, list_collection_runs

router = APIRouter(prefix="/collection-runs", tags=["collection-runs"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=CollectionRunListResponse)
def list_collection_runs_endpoint(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    creator_id: int | None = None,
    status: str | None = None,
    collector_type: str | None = None,
):
    items, total = list_collection_runs(
        db,
        page=page,
        page_size=page_size,
        creator_id=creator_id,
        status=status,
        collector_type=collector_type,
    )
    return CollectionRunListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{run_id}", response_model=CollectionRunRead)
def get_collection_run_endpoint(run_id: int, db: DbSession):
    run = get_collection_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="采集运行记录不存在")
    return run
