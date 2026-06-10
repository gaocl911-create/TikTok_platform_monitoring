from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.collectors.base import (
    CollectorConfigurationError,
    CollectorError,
    CollectorParseError,
    CollectorTransientError,
    ContentProfile,
    CreatorProfile,
)
from app.collectors.tikomni import (
    _dedupe,
    _dedupe_summary,
    _extract_aweme_id,
    _extract_post_dicts,
    _extract_single_work_dict,
    _fallback_creator_profile,
    _find_datetime,
    _find_image_url,
    _find_int,
    _find_int_with_presence,
    _find_statistics_dict,
    _find_string,
    _find_user_dict,
    _index_dicts_by_aweme_id,
    _infer_content_type,
    _is_success_code,
    _sec_user_id_from_creator,
    _to_decimal,
    _top_level_code,
    _unwrap_data,
)
from app.core.config import settings
from app.models.creator import CreatorAccount
from app.utils.profile_urls import normalize_profile_url

TIKHUB_SEC_USER_ID_ENDPOINT = "/api/v1/douyin/web/get_sec_user_id"
TIKHUB_PROFILE_ENDPOINT = "/api/v1/douyin/app/v3/handler_user_profile"
TIKHUB_USER_POSTS_ENDPOINT = "/api/v1/douyin/app/v3/fetch_user_post_videos"
TIKHUB_ONE_VIDEO_ENDPOINT = "/api/v1/douyin/app/v3/fetch_one_video_v3"
TIKHUB_ONE_VIDEO_BY_SHARE_URL_ENDPOINT = (
    "/api/v1/douyin/app/v3/fetch_one_video_by_share_url"
)

SUCCESS_CODES = {0, 200}
SUCCESS_STRINGS = {"0", "200", "success", "ok", "true"}


class TikHubBudgetExceeded(CollectorError):
    """Raised when the estimated TikHub daily budget would be exceeded."""


@dataclass(slots=True)
class TikHubUsage:
    request_count: int
    estimated_cost_usd: Decimal
    endpoints: list[str]
    budget_limited: bool
    budget_usd: Decimal
    spent_today_usd: Decimal


@dataclass(slots=True)
class TikHubResolvedCreator:
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


@dataclass(slots=True)
class TikHubResolvedWork:
    creator: TikHubResolvedCreator
    content: ContentProfile
    source_url: str
    raw_data: dict[str, Any]


class TikHubClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: int | None = None,
        daily_budget_usd: float | Decimal | None = None,
        estimated_unit_price_usd: float | Decimal | None = None,
        spent_today_usd: float | Decimal = 0,
    ) -> None:
        self.base_url = (base_url or settings.tikhub_api_base_url).rstrip("/")
        self.token = token if token is not None else settings.tikhub_api_token
        self.timeout_seconds = timeout_seconds or settings.tikhub_timeout_seconds
        self.daily_budget_usd = _to_decimal(
            settings.tikhub_daily_budget_usd
            if daily_budget_usd is None
            else daily_budget_usd
        )
        self.estimated_unit_price_usd = _to_decimal(
            settings.tikhub_estimated_unit_price_usd
            if estimated_unit_price_usd is None
            else estimated_unit_price_usd
        )
        self.spent_today_usd = _to_decimal(spent_today_usd)
        self.request_count = 0
        self.estimated_cost_usd = Decimal("0")
        self.endpoints: list[str] = []
        self.budget_limited = False

        if not self.token:
            raise CollectorConfigurationError("TIKHUB_API_TOKEN is not configured")

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", endpoint, params=params or {})

    def post(self, endpoint: str, payload: Any = None) -> dict[str, Any]:
        return self._request("POST", endpoint, payload={} if payload is None else payload)

    def usage_summary(self) -> dict[str, Any]:
        usage = TikHubUsage(
            request_count=self.request_count,
            estimated_cost_usd=self.estimated_cost_usd,
            endpoints=list(self.endpoints),
            budget_limited=self.budget_limited,
            budget_usd=self.daily_budget_usd,
            spent_today_usd=self.spent_today_usd,
        )
        remaining = max(
            Decimal("0"),
            usage.budget_usd - usage.spent_today_usd - usage.estimated_cost_usd,
        )
        return {
            "tikhub_request_count": usage.request_count,
            "tikhub_estimated_cost_usd": float(usage.estimated_cost_usd),
            "tikhub_spent_today_before_run_usd": float(usage.spent_today_usd),
            "tikhub_daily_budget_usd": float(usage.budget_usd),
            "tikhub_budget_remaining_usd": float(remaining),
            "tikhub_budget_limited": usage.budget_limited,
            "tikhub_endpoints": usage.endpoints,
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any = None,
    ) -> dict[str, Any]:
        self._check_budget(endpoint)
        request = self._build_request(endpoint, params or {}, method=method, payload=payload)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            self._raise_http_error(endpoint, exc)
        except TimeoutError as exc:
            raise CollectorTransientError(f"TikHub request timed out: {endpoint}") from exc
        except URLError as exc:
            raise CollectorTransientError(
                f"TikHub request failed: {endpoint}: {exc.reason}"
            ) from exc

        try:
            response_payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectorParseError(f"TikHub returned invalid JSON: {endpoint}") from exc

        self._validate_payload(endpoint, response_payload)
        self._record_success(endpoint)
        return response_payload

    def _build_request(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        method: str,
        payload: Any,
    ) -> Request:
        query = urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{self.base_url}{endpoint}"
        if query:
            url = f"{url}?{query}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "CreatorMonitor/1.0",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        return Request(url, data=data, headers=headers, method=method)

    def _check_budget(self, endpoint: str) -> None:
        if self.daily_budget_usd <= 0:
            return
        projected = (
            self.spent_today_usd
            + self.estimated_cost_usd
            + self.estimated_unit_price_usd
        )
        if projected > self.daily_budget_usd:
            self.budget_limited = True
            raise TikHubBudgetExceeded(
                f"TikHub daily budget would be exceeded before calling {endpoint}"
            )

    def _record_success(self, endpoint: str) -> None:
        self.request_count += 1
        self.estimated_cost_usd += self.estimated_unit_price_usd
        self.endpoints.append(endpoint)

    def _raise_http_error(self, endpoint: str, exc: HTTPError) -> None:
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            body = ""
        message = f"TikHub HTTP {exc.code} for {endpoint}"
        if body:
            message = f"{message}: {body}"
        if exc.code in {401, 403}:
            raise CollectorConfigurationError(message) from exc
        if exc.code == 429 or exc.code >= 500:
            raise CollectorTransientError(message) from exc
        raise CollectorError(message) from exc

    def _validate_payload(self, endpoint: str, payload: dict[str, Any]) -> None:
        code = _top_level_code(payload)
        if code is None or _is_success_code(code):
            return
        message = _find_string(payload, ("message", "msg", "error", "detail")) or str(code)
        if str(code) in {"401", "403"}:
            raise CollectorConfigurationError(f"TikHub API rejected credentials: {message}")
        if str(code) == "429" or str(code).startswith("5"):
            raise CollectorTransientError(
                f"TikHub API temporary failure at {endpoint}: {message}"
            )
        raise CollectorError(f"TikHub API error at {endpoint}: {message}")


class TikHubDouyinWorkResolver:
    collector_type = "tikhub_douyin"
    version = "tikhub-douyin-single-work-v1"

    def __init__(self, *, spent_today_usd: float | Decimal = 0) -> None:
        if not settings.tikhub_enabled:
            raise CollectorConfigurationError("TikHub collector is disabled")
        self.client = TikHubClient(spent_today_usd=spent_today_usd)
        self.warnings: list[str] = []

    def resolve(self, input_value: str) -> TikHubResolvedWork:
        source_url = normalize_profile_url(input_value)
        payload = self.client.get(
            TIKHUB_ONE_VIDEO_BY_SHARE_URL_ENDPOINT,
            {"share_url": source_url},
        )
        item = _extract_single_work_dict(_unwrap_data(payload))
        if not item:
            raise CollectorParseError("TikHub did not return Douyin work detail")

        creator = _map_resolved_work_creator(item)
        content = _map_content_profile(
            creator_nickname=creator.nickname,
            post=item,
            detail=item,
            statistics=_find_statistics_dict(item),
        )
        content.raw_data = {
            **(content.raw_data or {}),
            "tracking_mode": "single_work",
            "source_url": source_url,
            "single_work_payload": payload,
        }
        return TikHubResolvedWork(
            creator=creator,
            content=content,
            source_url=source_url,
            raw_data=payload,
        )

    def usage_summary(self) -> dict[str, Any]:
        return self.client.usage_summary()


class TikHubDouyinCollector:
    collector_type = "tikhub_douyin"
    version = "tikhub-douyin-v1"

    def __init__(self, *, spent_today_usd: float | Decimal = 0) -> None:
        if not settings.tikhub_enabled:
            raise CollectorConfigurationError("TikHub collector is disabled")
        self.client = TikHubClient(spent_today_usd=spent_today_usd)
        self.content_status = "pending"
        self.warnings: list[str] = []
        self._sec_user_id: str | None = None
        self._public_account_id: str | None = None
        self.last_seen_content_ids: list[str] = []
        self.new_content_ids: list[str] = []
        self.refreshed_content_ids: list[str] = []
        self.baseline_created = False

    def fetch_creator_profile(self, creator: CreatorAccount) -> CreatorProfile:
        try:
            sec_user_id = self._resolve_sec_user_id(creator)
            payload = self.client.get(TIKHUB_PROFILE_ENDPOINT, {"sec_user_id": sec_user_id})
        except TikHubBudgetExceeded as exc:
            self._mark_budget_limited(exc)
            return _fallback_creator_profile(creator)

        data = _unwrap_data(payload)
        user = _find_user_dict(data) or (data if isinstance(data, dict) else {})
        self._public_account_id = _find_string(
            user,
            ("unique_id", "short_id", "douyin_id", "display_id", "account_id"),
        )
        return CreatorProfile(
            nickname=_find_string(user, ("nickname", "name", "unique_id"))
            or creator.nickname,
            avatar_url=_find_image_url(
                user,
                ("avatar_thumb", "avatar_medium", "avatar_larger", "avatar_url", "avatar"),
            )
            or creator.avatar_url,
            bio=_find_string(user, ("signature", "desc", "description", "bio"))
            or creator.bio,
            verified_info=_find_string(
                user,
                ("custom_verify", "enterprise_verify_reason", "verify_info"),
            )
            or creator.verified_info,
            location=_find_string(user, ("ip_location", "province", "city", "location"))
            or creator.location,
            follower_count=_find_int(
                user,
                ("follower_count", "fans_count", "mplatform_followers_count"),
                default=creator.follower_count,
            ),
            following_count=_find_int(
                user,
                ("following_count", "follow_count"),
                default=creator.following_count,
            ),
            total_like_count=_find_int(
                user,
                ("total_favorited", "favorited_count", "total_like_count", "like_count"),
                default=creator.total_like_count,
            ),
            content_count=_find_int(
                user,
                ("aweme_count", "video_count", "content_count", "post_count"),
                default=creator.content_count,
            ),
        )

    def fetch_content_posts(self, creator: CreatorAccount) -> list[ContentProfile]:
        tracked_posts = _tracked_posts_from_creator(creator)
        tracked_content_ids = [post["platform_content_id"] for post in tracked_posts]
        monitor_scope = getattr(creator, "monitor_scope", "creator_collection")

        if monitor_scope == "single_content":
            if not tracked_content_ids:
                self.content_status = "no_new_content"
                return []
            details_by_id: dict[str, dict[str, Any]] = {}
            try:
                details_by_id = self._fetch_details_by_id(tracked_content_ids)
            except TikHubBudgetExceeded as exc:
                self._mark_budget_limited(exc)
            self.refreshed_content_ids = list(tracked_content_ids)
            profiles = [
                _map_tracked_content_profile(
                    tracked_post,
                    details_by_id.get(tracked_post["platform_content_id"], {}),
                )
                for tracked_post in tracked_posts
                if details_by_id.get(tracked_post["platform_content_id"], {})
                or self.content_status != "budget_limited"
            ]
            if self.content_status != "budget_limited":
                has_partial = any(profile.metrics_status == "partial" for profile in profiles)
                self.content_status = "partial" if has_partial else "metrics_refreshed"
            return profiles

        try:
            sec_user_id = self._resolve_sec_user_id(creator)
            posts_payload = self.client.get(
                TIKHUB_USER_POSTS_ENDPOINT,
                {
                    "sec_user_id": sec_user_id,
                    "max_cursor": 0,
                    "count": 20,
                    "sort_type": 0,
                },
            )
        except TikHubBudgetExceeded as exc:
            self._mark_budget_limited(exc)
            return []

        post_dicts = _extract_post_dicts(_unwrap_data(posts_payload))
        indexed_posts = {
            aweme_id: post
            for post in post_dicts
            if (aweme_id := _extract_aweme_id(post))
        }
        aweme_ids = list(indexed_posts)
        self.last_seen_content_ids = aweme_ids
        known_ids = set(getattr(creator, "known_content_ids", []) or [])
        if not known_ids:
            known_ids = set(getattr(creator, "baseline_content_ids", []) or [])

        if aweme_ids and not known_ids:
            self.baseline_created = True
            self.content_status = "baseline_created"
            self.warnings.append(
                "Content baseline established; historical posts are not imported."
            )
            return []

        self.new_content_ids = [aweme_id for aweme_id in aweme_ids if aweme_id not in known_ids]
        self.refreshed_content_ids = _dedupe(
            content_id for content_id in tracked_content_ids if content_id not in self.new_content_ids
        )
        content_ids = _dedupe([*self.new_content_ids, *self.refreshed_content_ids])
        if not self.new_content_ids and not self.refreshed_content_ids:
            self.content_status = "no_new_content"
            return []

        details_by_id: dict[str, dict[str, Any]] = {}
        try:
            details_by_id = self._fetch_details_by_id(content_ids)
        except TikHubBudgetExceeded as exc:
            self._mark_budget_limited(exc)

        profiles: list[ContentProfile] = []
        for aweme_id in self.new_content_ids:
            post = indexed_posts[aweme_id]
            detail = details_by_id.get(aweme_id, {})
            profiles.append(
                _map_content_profile(
                    creator_nickname=creator.nickname,
                    post=post,
                    detail=detail,
                    statistics=_find_statistics_dict(detail),
                )
            )
        for tracked_post in tracked_posts:
            aweme_id = tracked_post["platform_content_id"]
            if aweme_id in self.new_content_ids:
                continue
            detail = details_by_id.get(aweme_id, {})
            if not detail and self.content_status == "budget_limited":
                continue
            profiles.append(_map_tracked_content_profile(tracked_post, detail))

        if self.content_status != "budget_limited":
            has_partial = any(profile.metrics_status == "partial" for profile in profiles)
            if has_partial:
                self.content_status = "partial"
            elif self.new_content_ids:
                self.content_status = "success"
            else:
                self.content_status = "metrics_refreshed"
        return profiles

    def usage_summary(self) -> dict[str, Any]:
        return self.client.usage_summary()

    def _resolve_sec_user_id(self, creator: CreatorAccount) -> str:
        candidate = _sec_user_id_from_creator(creator)
        if candidate:
            self._sec_user_id = candidate
            return candidate
        payload = self.client.get(TIKHUB_SEC_USER_ID_ENDPOINT, {"url": creator.profile_url})
        data = _unwrap_data(payload)
        sec_user_id = _find_string(data, ("sec_user_id", "secUid", "sec_uid", "secUserId"))
        if not sec_user_id and isinstance(data, str) and data.startswith("MS4w"):
            sec_user_id = data
        if not sec_user_id:
            raise CollectorParseError("TikHub did not return sec_user_id")
        self._sec_user_id = sec_user_id
        return sec_user_id

    def _fetch_details_by_id(self, aweme_ids: list[str]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for aweme_id in aweme_ids:
            payload = self.client.get(TIKHUB_ONE_VIDEO_ENDPOINT, {"aweme_id": aweme_id})
            item = _extract_single_work_dict(_unwrap_data(payload))
            if item:
                indexed.update(_index_dicts_by_aweme_id(item, [aweme_id]))
                if aweme_id not in indexed:
                    indexed[aweme_id] = item
        return indexed

    def _mark_budget_limited(self, exc: TikHubBudgetExceeded) -> None:
        self.content_status = "budget_limited"
        self.warnings.append(str(exc))


def _map_resolved_work_creator(item: dict[str, Any]) -> TikHubResolvedCreator:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    aweme_id = _extract_aweme_id(item) or "unknown"
    sec_uid = _find_string(author, ("sec_uid", "sec_user_id", "secUid", "secUserId"))
    author_uid = (
        _find_string(author, ("uid", "id", "user_id"))
        or _find_string(item, ("author_user_id",))
    )
    display_id = _find_string(
        author,
        ("unique_id", "short_id", "douyin_id", "display_id", "account_id"),
    )
    nickname = _find_string(author, ("nickname", "name")) or display_id or f"Author {aweme_id[-6:]}"
    platform_account_id = sec_uid or author_uid or display_id or f"unknown-author-{aweme_id}"
    profile_url = (
        f"https://www.douyin.com/user/{sec_uid}"
        if sec_uid
        else f"https://www.douyin.com/user/{platform_account_id}"
    )
    return TikHubResolvedCreator(
        platform_account_id=platform_account_id[:128],
        platform_display_id=display_id[:128] if display_id else None,
        nickname=nickname[:128],
        profile_url=profile_url,
        avatar_url=_find_image_url(
            author,
            ("avatar_thumb", "avatar_medium", "avatar_larger", "avatar_url", "avatar"),
        ),
        bio=_find_string(author, ("signature", "desc", "description", "bio")),
        verified_info=_find_string(
            author,
            ("custom_verify", "enterprise_verify_reason", "verify_info"),
        ),
        location=_find_string(author, ("ip_location", "province", "city", "location")),
        follower_count=_find_int(
            author,
            ("follower_count", "fans_count", "mplatform_followers_count"),
            default=0,
        ),
        following_count=_find_int(author, ("following_count", "follow_count"), default=0),
        total_like_count=_find_int(
            author,
            ("total_favorited", "favorited_count", "total_like_count", "like_count"),
            default=0,
        ),
        content_count=_find_int(
            author,
            ("aweme_count", "video_count", "content_count", "post_count"),
            default=0,
        ),
    )


def _map_content_profile(
    *,
    creator_nickname: str,
    post: dict[str, Any],
    detail: dict[str, Any],
    statistics: dict[str, Any],
) -> ContentProfile:
    merged_sources = (statistics, detail, post)
    aweme_id = _extract_aweme_id(post) or _extract_aweme_id(detail) or _extract_aweme_id(statistics)
    if not aweme_id:
        raise CollectorParseError("TikHub post is missing aweme_id")

    title = (
        _find_string(merged_sources, ("desc", "title", "caption", "share_title"))
        or f"{creator_nickname} content {aweme_id[-6:]}"
    )
    summary = _dedupe_summary(
        title,
        _find_string(merged_sources, ("desc", "caption", "share_desc")),
    )
    content_url = (
        _find_string(merged_sources, ("share_url", "url", "content_url"))
        or f"https://www.douyin.com/video/{aweme_id}"
    )
    cover_url = _find_image_url(
        merged_sources,
        ("cover", "video_cover", "origin_cover", "dynamic_cover", "images", "image_infos"),
    )
    published_at = _find_datetime(merged_sources, ("create_time", "publish_time", "published_at"))
    content_type = _infer_content_type(merged_sources)
    like_count, like_present = _find_int_with_presence(
        merged_sources,
        ("digg_count", "like_count", "liked_count"),
    )
    comment_count, comment_present = _find_int_with_presence(
        merged_sources,
        ("comment_count", "comments_count"),
    )
    collect_count, collect_present = _find_int_with_presence(
        merged_sources,
        ("collect_count", "collects_count", "favorite_count", "favorites_count"),
    )
    share_count, share_present = _find_int_with_presence(
        merged_sources,
        ("share_count", "share_num", "shares_count"),
    )
    missing = [
        name
        for name, present in {
            "like_count": like_present,
            "comment_count": comment_present,
            "collect_count": collect_present,
            "share_count": share_present,
        }.items()
        if not present
    ]
    return ContentProfile(
        platform_content_id=aweme_id,
        title=title[:500],
        summary=summary,
        content_type=content_type,
        content_url=content_url,
        cover_url=cover_url,
        published_at=published_at,
        like_count=like_count,
        comment_count=comment_count,
        collect_count=collect_count,
        share_count=share_count,
        metrics_status="partial" if missing else "success",
        raw_data={
            "data_source": "tikhub_douyin",
            "detail": detail or None,
            "statistics": statistics or None,
            "missing_metrics": missing,
        },
    )


def _map_tracked_content_profile(
    tracked_post: dict[str, Any],
    detail: dict[str, Any],
) -> ContentProfile:
    statistics = _find_statistics_dict(detail) if detail else {}
    like_count, like_present = _find_int_with_presence(
        (statistics, detail),
        ("digg_count", "like_count", "liked_count"),
    )
    comment_count, comment_present = _find_int_with_presence(
        (statistics, detail),
        ("comment_count", "comments_count"),
    )
    collect_count, collect_present = _find_int_with_presence(
        (statistics, detail),
        ("collect_count", "collects_count", "favorite_count", "favorites_count"),
    )
    share_count, share_present = _find_int_with_presence(
        (statistics, detail),
        ("share_count", "share_num", "shares_count"),
    )
    missing = [
        name
        for name, present in {
            "like_count": like_present,
            "comment_count": comment_present,
            "collect_count": collect_present,
            "share_count": share_present,
        }.items()
        if not present
    ]
    title = (
        _find_string(detail, ("desc", "title", "caption", "share_title"))
        or tracked_post["title"]
    )
    summary = _dedupe_summary(
        title,
        _find_string(detail, ("desc", "caption", "share_desc"))
        or tracked_post.get("summary"),
    )
    return ContentProfile(
        platform_content_id=tracked_post["platform_content_id"],
        title=title,
        summary=summary,
        content_type=_infer_content_type(detail) if detail else tracked_post["content_type"],
        content_url=_find_string(detail, ("share_url", "url", "content_url"))
        or tracked_post["content_url"],
        cover_url=_find_image_url(
            detail,
            ("cover", "video_cover", "origin_cover", "dynamic_cover", "images", "image_infos"),
        )
        or tracked_post.get("cover_url"),
        published_at=_find_datetime(detail, ("create_time", "publish_time", "published_at"))
        or tracked_post.get("published_at"),
        like_count=like_count if like_present else tracked_post["latest_like_count"],
        comment_count=comment_count if comment_present else tracked_post["latest_comment_count"],
        collect_count=collect_count if collect_present else tracked_post["latest_collect_count"],
        share_count=share_count if share_present else tracked_post["latest_share_count"],
        metrics_status="partial" if missing else "success",
        raw_data={
            "data_source": "tikhub_douyin",
            "tracking_refresh": True,
            "detail": detail or None,
            "missing_metrics": missing,
        },
    )


def _tracked_posts_from_creator(creator: CreatorAccount) -> list[dict[str, Any]]:
    tracked_posts: list[dict[str, Any]] = []
    for item in getattr(creator, "tracked_content_posts", []) or []:
        platform_content_id = str(_get_attr(item, "platform_content_id", "")).strip()
        if not platform_content_id:
            continue
        tracked_posts.append(
            {
                "platform_content_id": platform_content_id,
                "title": _get_attr(item, "title", f"Douyin content {platform_content_id}"),
                "summary": _get_attr(item, "summary", None),
                "content_type": _get_attr(item, "content_type", "video"),
                "content_url": _get_attr(
                    item,
                    "content_url",
                    f"https://www.douyin.com/video/{platform_content_id}",
                ),
                "cover_url": _get_attr(item, "cover_url", None),
                "published_at": _get_attr(item, "published_at", None),
                "latest_like_count": int(_get_attr(item, "latest_like_count", 0) or 0),
                "latest_comment_count": int(_get_attr(item, "latest_comment_count", 0) or 0),
                "latest_collect_count": int(_get_attr(item, "latest_collect_count", 0) or 0),
                "latest_share_count": int(_get_attr(item, "latest_share_count", 0) or 0),
            }
        )
    return tracked_posts


def _get_attr(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)
