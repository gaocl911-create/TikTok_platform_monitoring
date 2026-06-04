from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.content import ContentPostListResponse, ContentPostRead, ContentSnapshotRead
from app.services.posts import get_post, list_post_snapshots, list_posts

router = APIRouter(prefix="/posts", tags=["content"])
DbSession = Annotated[Session, Depends(get_db)]


def require_post(db: Session, post_id: int):
    post = get_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容不存在")
    return post


@router.get("", response_model=ContentPostListResponse)
def list_posts_endpoint(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    creator_id: int | None = None,
    platform: str | None = None,
    search: str | None = None,
):
    items, total = list_posts(
        db,
        page=page,
        page_size=page_size,
        creator_id=creator_id,
        platform=platform,
        search=search,
    )
    return ContentPostListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{post_id}", response_model=ContentPostRead)
def get_post_endpoint(post_id: int, db: DbSession):
    return require_post(db, post_id)


@router.get("/{post_id}/snapshots", response_model=list[ContentSnapshotRead])
def list_post_snapshots_endpoint(
    post_id: int,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
):
    require_post(db, post_id)
    return list_post_snapshots(db, post_id, limit=limit)
