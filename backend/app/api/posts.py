from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors import CollectorError
from app.core.database import get_db
from app.models.content_post import ContentPost
from app.models.creator import CreatorAccount
from app.schemas.content import (
    ContentCreatorPreview,
    ContentLinkCreateRequest,
    ContentLinkCreateResponse,
    ContentLinkResolveRequest,
    ContentLinkResolveResponse,
    ContentPostListResponse,
    ContentPostRead,
    ContentSnapshotRead,
    ContentWorkPreview,
)
from app.services.posts import (
    add_content_from_link,
    cache_resolved_content_link,
    get_post,
    list_post_snapshots,
    list_posts,
    resolve_content_link,
)

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


@router.post("/resolve-link", response_model=ContentLinkResolveResponse)
def resolve_post_link_endpoint(payload: ContentLinkResolveRequest, db: DbSession):
    try:
        resolved, _usage, warnings = resolve_content_link(
            db,
            platform=payload.platform,
            input_value=payload.input_value,
        )
    except CollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    existing_creator = _find_existing_creator(
        db,
        resolved.creator.platform_account_id,
        resolved.creator.platform_display_id,
    )
    existing_post = None
    if existing_creator is not None:
        existing_post = db.scalar(
            select(ContentPost).where(
                ContentPost.creator_id == existing_creator.id,
                ContentPost.platform_content_id == resolved.content.platform_content_id,
            )
        )
    resolve_token = cache_resolved_content_link(
        platform=payload.platform,
        input_value=payload.input_value,
        resolved=resolved,
        usage_summary=_usage,
        warnings=warnings,
    )
    return _resolve_response(
        resolved,
        warnings=warnings,
        resolve_token=resolve_token,
        existing_creator_id=existing_creator.id if existing_creator else None,
        existing_post_id=existing_post.id if existing_post else None,
    )


@router.post("/from-link", response_model=ContentLinkCreateResponse, status_code=status.HTTP_201_CREATED)
def add_post_from_link_endpoint(payload: ContentLinkCreateRequest, db: DbSession):
    try:
        result = add_content_from_link(
            db,
            platform=payload.platform,
            input_value=payload.input_value,
            creator_id=payload.creator_id,
            group_name=payload.group_name,
            tags=payload.tags,
            monitor_interval_minutes=payload.monitor_interval_minutes,
            resolve_token=payload.resolve_token,
        )
    except CollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return ContentLinkCreateResponse(
        post=result.post,
        creator_created=result.creator_created,
        post_created=result.post_created,
        run_id=result.run.id,
        warnings=result.warnings,
    )


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


def _find_existing_creator(
    db: Session,
    platform_account_id: str,
    platform_display_id: str | None,
) -> CreatorAccount | None:
    creator = db.scalar(
        select(CreatorAccount).where(
            CreatorAccount.platform == "douyin",
            CreatorAccount.platform_account_id == platform_account_id,
        )
    )
    if creator is not None or not platform_display_id:
        return creator
    return db.scalar(
        select(CreatorAccount).where(
            CreatorAccount.platform == "douyin",
            CreatorAccount.platform_display_id == platform_display_id,
        )
    )


def _resolve_response(
    resolved,
    *,
    warnings: list[str],
    resolve_token: str | None,
    existing_creator_id: int | None,
    existing_post_id: int | None,
) -> ContentLinkResolveResponse:
    return ContentLinkResolveResponse(
        platform="douyin",
        source_url=resolved.source_url,
        resolve_token=resolve_token,
        creator=ContentCreatorPreview(
            platform_account_id=resolved.creator.platform_account_id,
            platform_display_id=resolved.creator.platform_display_id,
            nickname=resolved.creator.nickname,
            profile_url=resolved.creator.profile_url,
            avatar_url=resolved.creator.avatar_url,
            bio=resolved.creator.bio,
            location=resolved.creator.location,
        ),
        content=ContentWorkPreview(
            platform_content_id=resolved.content.platform_content_id,
            title=resolved.content.title,
            summary=resolved.content.summary,
            content_type=resolved.content.content_type,
            content_url=resolved.content.content_url,
            cover_url=resolved.content.cover_url,
            published_at=resolved.content.published_at,
            like_count=resolved.content.like_count,
            comment_count=resolved.content.comment_count,
            collect_count=resolved.content.collect_count,
            share_count=resolved.content.share_count,
            metrics_status=resolved.content.metrics_status,
        ),
        existing_creator_id=existing_creator_id,
        existing_post_id=existing_post_id,
        warnings=warnings,
    )
