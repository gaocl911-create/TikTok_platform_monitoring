from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.collectors.base import (
    CollectorConfigurationError,
    CollectorError,
    CollectorParseError,
    CollectorTransientError,
    CollectorValidationError,
    ContentProfile,
    CreatorProfile,
)
from app.core.config import settings
from app.models.creator import CreatorAccount
from app.utils.profile_urls import normalize_profile_url

DOUYIN_SEC_USER_ID_ENDPOINT = "/api/u1/v1/douyin/web/get_sec_user_id"
DOUYIN_WEB_PROFILE_ENDPOINT = "/api/u1/v1/douyin/app/v3/handler_user_profile"
DOUYIN_USER_POSTS_ENDPOINT = "/api/u1/v1/douyin/app/v3/fetch_user_post_videos"
DOUYIN_MULTI_VIDEO_ENDPOINT = "/api/u1/v1/douyin/app/v3/fetch_multi_video"
DOUYIN_MULTI_STATISTICS_ENDPOINT = "/api/u1/v1/douyin/app/v3/fetch_multi_video_statistics"
DOUYIN_ONE_VIDEO_APP_ENDPOINT = "/api/u1/v1/douyin/app/v3/fetch_one_video_by_share_url"
DOUYIN_ONE_VIDEO_WEB_ENDPOINT = "/api/u1/v1/douyin/web/fetch_one_video_by_share_url"

SUCCESS_CODES = {0, 200}
SUCCESS_STRINGS = {"0", "200", "success", "ok", "true"}


class TikOmniBudgetExceeded(CollectorError):
    """Raised when the estimated TikOmni daily budget would be exceeded."""


@dataclass(slots=True)
class TikOmniUsage:
    request_count: int
    estimated_cost_cny: Decimal
    endpoints: list[str]
    budget_limited: bool
    budget_cny: Decimal
    spent_today_cny: Decimal


@dataclass(slots=True)
class TikOmniResolvedCreator:
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
class TikOmniResolvedWork:
    creator: TikOmniResolvedCreator
    content: ContentProfile
    source_url: str
    raw_data: dict[str, Any]


class TikOmniClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: int | None = None,
        daily_budget_cny: float | Decimal | None = None,
        estimated_unit_price_cny: float | Decimal | None = None,
        spent_today_cny: float | Decimal = 0,
    ) -> None:
        self.base_url = (base_url or settings.tikomni_api_base_url).rstrip("/")
        self.token = token if token is not None else settings.tikomni_api_token
        self.timeout_seconds = timeout_seconds or settings.tikomni_timeout_seconds
        self.daily_budget_cny = _to_decimal(
            settings.tikomni_daily_budget_cny
            if daily_budget_cny is None
            else daily_budget_cny
        )
        self.estimated_unit_price_cny = _to_decimal(
            settings.tikomni_estimated_unit_price_cny
            if estimated_unit_price_cny is None
            else estimated_unit_price_cny
        )
        self.spent_today_cny = _to_decimal(spent_today_cny)
        self.request_count = 0
        self.estimated_cost_cny = Decimal("0")
        self.endpoints: list[str] = []
        self.budget_limited = False

        if not self.token:
            raise CollectorConfigurationError("TIKOMNI_API_TOKEN is not configured")

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", endpoint, params=params or {})

    def post(self, endpoint: str, payload: Any = None) -> dict[str, Any]:
        return self._request("POST", endpoint, payload=[] if payload is None else payload)

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
            raise CollectorTransientError(f"TikOmni request timed out: {endpoint}") from exc
        except URLError as exc:
            raise CollectorTransientError(
                f"TikOmni request failed: {endpoint}: {exc.reason}"
            ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectorParseError(f"TikOmni returned invalid JSON: {endpoint}") from exc

        self._validate_payload(endpoint, payload)
        self._record_success(endpoint)
        return payload

    def usage_summary(self) -> dict[str, Any]:
        usage = TikOmniUsage(
            request_count=self.request_count,
            estimated_cost_cny=self.estimated_cost_cny,
            endpoints=list(self.endpoints),
            budget_limited=self.budget_limited,
            budget_cny=self.daily_budget_cny,
            spent_today_cny=self.spent_today_cny,
        )
        remaining = max(
            Decimal("0"),
            usage.budget_cny - usage.spent_today_cny - usage.estimated_cost_cny,
        )
        return {
            "tikomni_request_count": usage.request_count,
            "tikomni_estimated_cost_cny": float(usage.estimated_cost_cny),
            "tikomni_spent_today_before_run_cny": float(usage.spent_today_cny),
            "tikomni_daily_budget_cny": float(usage.budget_cny),
            "tikomni_budget_remaining_cny": float(remaining),
            "tikomni_budget_limited": usage.budget_limited,
            "tikomni_endpoints": usage.endpoints,
        }

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
        return Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

    def _check_budget(self, endpoint: str) -> None:
        if self.daily_budget_cny <= 0:
            return
        projected = (
            self.spent_today_cny
            + self.estimated_cost_cny
            + self.estimated_unit_price_cny
        )
        if projected > self.daily_budget_cny:
            self.budget_limited = True
            raise TikOmniBudgetExceeded(
                f"TikOmni daily budget would be exceeded before calling {endpoint}"
            )

    def _record_success(self, endpoint: str) -> None:
        self.request_count += 1
        self.estimated_cost_cny += self.estimated_unit_price_cny
        self.endpoints.append(endpoint)

    def _raise_http_error(self, endpoint: str, exc: HTTPError) -> None:
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            body = ""
        friendly_message = _friendly_tikomni_http_error(endpoint, exc.code, body)
        if friendly_message:
            raise CollectorValidationError(friendly_message) from exc
        message = f"TikOmni HTTP {exc.code} for {endpoint}"
        if body:
            message = f"{message}: {body}"
        if exc.code in {401, 403}:
            raise CollectorConfigurationError(message) from exc
        if exc.code == 429 or exc.code >= 500:
            raise CollectorTransientError(message) from exc
        raise CollectorError(message) from exc

    def _validate_payload(self, endpoint: str, payload: dict[str, Any]) -> None:
        code = _top_level_code(payload)
        if code is None:
            return
        if _is_success_code(code):
            return
        message = _find_string(payload, ("message", "msg", "error", "detail")) or str(code)
        if str(code) in {"401", "403"}:
            raise CollectorConfigurationError(f"TikOmni API rejected credentials: {message}")
        if str(code) == "429" or str(code).startswith("5"):
            raise CollectorTransientError(f"TikOmni API temporary failure at {endpoint}: {message}")
        raise CollectorError(f"TikOmni API error at {endpoint}: {message}")


class TikOmniDouyinWorkResolver:
    collector_type = "tikomni_douyin"
    version = "tikomni-douyin-single-work-v1"

    def __init__(self, *, spent_today_cny: float | Decimal = 0) -> None:
        if not settings.tikomni_enabled:
            raise CollectorConfigurationError("TikOmni collector is disabled")
        self.client = TikOmniClient(spent_today_cny=spent_today_cny)
        self.warnings: list[str] = []

    def resolve(self, input_value: str) -> TikOmniResolvedWork:
        source_url = normalize_profile_url(input_value)
        app_payload: dict[str, Any] | None = None
        try:
            app_payload = self.client.get(
                DOUYIN_ONE_VIDEO_APP_ENDPOINT,
                {"share_url": source_url},
            )
            item = _extract_single_work_dict(_unwrap_data(app_payload))
        except CollectorError as exc:
            self.warnings.append(f"App endpoint failed, trying web endpoint: {exc}")
            item = None

        if item is None:
            web_payload = self.client.get(
                DOUYIN_ONE_VIDEO_WEB_ENDPOINT,
                {"share_url": source_url},
            )
            item = _extract_single_work_dict(_unwrap_data(web_payload))
            payload = web_payload
        else:
            payload = app_payload or {}

        if not item:
            raise CollectorParseError("TikOmni did not return Douyin work detail")

        creator = _map_resolved_work_creator(item)
        content = _map_content_profile(
            SimpleCreatorForWork(
                id=0,
                platform="douyin",
                nickname=creator.nickname,
                collector_type=self.collector_type,
            ),
            item,
            item,
            _find_statistics_dict(item),
        )
        content.raw_data = {
            **(content.raw_data or {}),
            "tracking_mode": "single_work",
            "source_url": source_url,
            "single_work_payload": payload,
        }
        return TikOmniResolvedWork(
            creator=creator,
            content=content,
            source_url=source_url,
            raw_data=payload,
        )

    def usage_summary(self) -> dict[str, Any]:
        return self.client.usage_summary()


@dataclass(slots=True)
class SimpleCreatorForWork:
    id: int
    platform: str
    nickname: str
    collector_type: str


class TikOmniDouyinCollector:
    collector_type = "tikomni_douyin"
    version = "tikomni-douyin-v1"

    def __init__(self, *, spent_today_cny: float | Decimal = 0) -> None:
        if not settings.tikomni_enabled:
            raise CollectorConfigurationError("TikOmni collector is disabled")
        self.client = TikOmniClient(spent_today_cny=spent_today_cny)
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
            payload = self.client.get(
                DOUYIN_WEB_PROFILE_ENDPOINT,
                {"sec_user_id": sec_user_id},
            )
        except TikOmniBudgetExceeded as exc:
            self._mark_budget_limited(exc)
            return _fallback_creator_profile(creator)

        data = _unwrap_data(payload)
        user = _find_user_dict(data) or (data if isinstance(data, dict) else {})

        nickname = _find_string(user, ("nickname", "name", "unique_id")) or creator.nickname
        self._public_account_id = _find_string(
            user,
            ("unique_id", "short_id", "douyin_id", "display_id", "account_id"),
        )
        avatar_url = _find_image_url(
            user,
            ("avatar_thumb", "avatar_medium", "avatar_larger", "avatar_url", "avatar"),
        )
        bio = _find_string(user, ("signature", "desc", "description", "bio")) or creator.bio
        verified_info = _find_string(
            user,
            ("custom_verify", "enterprise_verify_reason", "verify_info"),
        )
        location = (
            _find_string(user, ("ip_location", "province", "city", "location"))
            or creator.location
        )
        follower_count = _find_int(
            user,
            ("follower_count", "fans_count", "mplatform_followers_count"),
            default=creator.follower_count,
        )
        following_count = _find_int(
            user,
            ("following_count", "follow_count"),
            default=creator.following_count,
        )
        total_like_count = _find_int(
            user,
            ("total_favorited", "favorited_count", "total_like_count", "like_count"),
            default=creator.total_like_count,
        )
        content_count = _find_int(
            user,
            ("aweme_count", "video_count", "content_count", "post_count"),
            default=creator.content_count,
        )

        return CreatorProfile(
            nickname=nickname,
            avatar_url=avatar_url or creator.avatar_url,
            bio=bio,
            verified_info=verified_info or creator.verified_info,
            location=location,
            follower_count=follower_count,
            following_count=following_count,
            total_like_count=total_like_count,
            content_count=content_count,
        )

    def fetch_content_posts(self, creator: CreatorAccount) -> list[ContentProfile]:
        tracked_posts = _tracked_posts_from_creator(creator)
        tracked_content_ids = [post["platform_content_id"] for post in tracked_posts]
        monitor_scope = getattr(creator, "monitor_scope", "creator_collection")

        if monitor_scope == "single_content":
            if not tracked_content_ids:
                self.content_status = "no_new_content"
                return []
            statistics_by_id: dict[str, dict[str, Any]] = {}
            try:
                statistics_by_id = self._fetch_statistics_by_id(tracked_content_ids)
            except TikOmniBudgetExceeded as exc:
                self._mark_budget_limited(exc)
            self.refreshed_content_ids = list(tracked_content_ids)
            profiles = [
                _map_tracked_content_profile(
                    tracked_post,
                    statistics_by_id.get(tracked_post["platform_content_id"], {}),
                )
                for tracked_post in tracked_posts
                if statistics_by_id.get(tracked_post["platform_content_id"], {})
                or self.content_status != "budget_limited"
            ]
            if self.content_status != "budget_limited":
                has_partial = any(profile.metrics_status == "partial" for profile in profiles)
                self.content_status = "partial" if has_partial else "metrics_refreshed"
            return profiles

        try:
            sec_user_id = self._resolve_sec_user_id(creator)
            posts_payload = self.client.get(
                DOUYIN_USER_POSTS_ENDPOINT,
                {
                    "sec_user_id": sec_user_id,
                    "max_cursor": 0,
                    "count": 20,
                    "sort_type": 0,
                },
            )
        except TikOmniBudgetExceeded as exc:
            self._mark_budget_limited(exc)
            return []

        post_dicts = _extract_post_dicts(_unwrap_data(posts_payload))
        indexed_posts: dict[str, dict[str, Any]] = {}
        for post in post_dicts:
            aweme_id = _extract_aweme_id(post)
            if not aweme_id:
                self.warnings.append("TikOmni returned a post without aweme_id")
                continue
            if aweme_id not in indexed_posts:
                indexed_posts[aweme_id] = post

        aweme_ids = list(indexed_posts)
        self.last_seen_content_ids = aweme_ids
        known_ids = set(getattr(creator, "known_content_ids", []) or [])
        if not known_ids:
            known_ids = set(getattr(creator, "baseline_content_ids", []) or [])

        if aweme_ids and not known_ids:
            self.baseline_created = True
            self.content_status = "baseline_created"
            self.warnings.append("已建立作品基线，历史作品不会进入内容动态。")
            return []

        self.new_content_ids = [aweme_id for aweme_id in aweme_ids if aweme_id not in known_ids]
        self.refreshed_content_ids = _dedupe(
            content_id for content_id in tracked_content_ids if content_id not in self.new_content_ids
        )
        metrics_content_ids = _dedupe([*self.new_content_ids, *self.refreshed_content_ids])
        if not self.new_content_ids and not self.refreshed_content_ids:
            self.content_status = "no_new_content"
            return []

        details_by_id: dict[str, dict[str, Any]] = {}
        statistics_by_id: dict[str, dict[str, Any]] = {}

        try:
            if self.new_content_ids:
                details_by_id = self._fetch_details_by_id(self.new_content_ids)
            if metrics_content_ids:
                statistics_by_id = self._fetch_statistics_by_id(metrics_content_ids)
        except TikOmniBudgetExceeded as exc:
            self._mark_budget_limited(exc)

        profiles: list[ContentProfile] = []
        for aweme_id in self.new_content_ids:
            post = indexed_posts[aweme_id]
            detail = details_by_id.get(aweme_id, {})
            statistics = statistics_by_id.get(aweme_id, {})
            profiles.append(_map_content_profile(creator, post, detail, statistics))

        for tracked_post in tracked_posts:
            aweme_id = tracked_post["platform_content_id"]
            if aweme_id in self.new_content_ids:
                continue
            statistics = statistics_by_id.get(aweme_id, {})
            if not statistics and self.content_status == "budget_limited":
                continue
            profiles.append(_map_tracked_content_profile(tracked_post, statistics))

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
        if self._sec_user_id:
            return self._sec_user_id

        candidate = _sec_user_id_from_creator(creator)
        if candidate:
            self._sec_user_id = candidate
            return candidate

        payload = self.client.get(DOUYIN_SEC_USER_ID_ENDPOINT, {"url": creator.profile_url})
        data = _unwrap_data(payload)
        sec_user_id = _find_string(data, ("sec_user_id", "secUid", "sec_uid", "secUserId"))
        if not sec_user_id and isinstance(data, str) and data.startswith("MS4w"):
            sec_user_id = data
        if not sec_user_id:
            raise CollectorParseError("TikOmni did not return sec_user_id for the Douyin profile")
        self._sec_user_id = sec_user_id
        return sec_user_id

    def _fetch_details_by_id(self, aweme_ids: list[str]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for chunk in _chunks(aweme_ids, 10):
            payload = self.client.post(
                DOUYIN_MULTI_VIDEO_ENDPOINT,
                chunk,
            )
            indexed.update(_index_dicts_by_aweme_id(_unwrap_data(payload), chunk))
        return indexed

    def _fetch_statistics_by_id(self, aweme_ids: list[str]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for chunk in _chunks(aweme_ids, 50):
            payload = self.client.get(
                DOUYIN_MULTI_STATISTICS_ENDPOINT,
                {"aweme_ids": ",".join(chunk)},
            )
            indexed.update(_index_dicts_by_aweme_id(_unwrap_data(payload), chunk))
        return indexed

    def _mark_budget_limited(self, exc: TikOmniBudgetExceeded) -> None:
        self.content_status = "budget_limited"
        self.warnings.append(str(exc))


def _fallback_creator_profile(creator: CreatorAccount) -> CreatorProfile:
    return CreatorProfile(
        nickname=creator.nickname,
        avatar_url=creator.avatar_url,
        bio=creator.bio,
        verified_info=creator.verified_info,
        location=creator.location,
        follower_count=creator.follower_count,
        following_count=creator.following_count,
        total_like_count=creator.total_like_count,
        content_count=creator.content_count,
    )


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _friendly_tikomni_http_error(endpoint: str, status_code: int, body: str) -> str | None:
    if status_code != 400 or endpoint not in {
        DOUYIN_ONE_VIDEO_APP_ENDPOINT,
        DOUYIN_ONE_VIDEO_WEB_ENDPOINT,
    }:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}
    message = str(payload.get("message") or "").lower()
    params = payload.get("params") if isinstance(payload, dict) else {}
    share_url = str(params.get("share_url") or "") if isinstance(params, dict) else ""
    if "invalid request parameters" not in message:
        return None
    if "v.douyin.com" in share_url:
        return "这个抖音短链无法被 TikOmni 识别，可能已失效或复制不完整；请重新复制作品分享链接，或粘贴 www.douyin.com/video/... 完整作品链接"
    return "TikOmni 不接受当前作品链接参数，请换成抖音作品页完整链接后重试"


def _extract_single_work_dict(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        direct = data.get("aweme_detail") or data.get("aweme_info")
        if isinstance(direct, dict):
            return direct
        for key in ("aweme_details", "aweme_list", "item_list", "items", "list"):
            value = data.get(key)
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    return first
            if isinstance(value, dict):
                return value
        if _extract_aweme_id(data):
            return data
        for value in data.values():
            hit = _extract_single_work_dict(value)
            if hit:
                return hit
    if isinstance(data, list):
        for item in data:
            hit = _extract_single_work_dict(item)
            if hit:
                return hit
    return None


def _find_statistics_dict(data: dict[str, Any]) -> dict[str, Any]:
    statistics = data.get("statistics")
    return statistics if isinstance(statistics, dict) else data


def _map_resolved_work_creator(item: dict[str, Any]) -> TikOmniResolvedCreator:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    aweme_id = _extract_aweme_id(item) or "unknown"
    sec_uid = _find_string(
        author,
        ("sec_uid", "sec_user_id", "secUid", "secUserId"),
    )
    author_uid = (
        _find_string(author, ("uid", "id", "user_id"))
        or _find_string(item, ("author_user_id",))
    )
    display_id = _find_string(
        author,
        ("unique_id", "short_id", "douyin_id", "display_id", "account_id"),
    )
    nickname = _find_string(author, ("nickname", "name")) or display_id or f"作者 {aweme_id[-6:]}"
    platform_account_id = sec_uid or author_uid or display_id or f"unknown-author-{aweme_id}"
    profile_url = (
        f"https://www.douyin.com/user/{sec_uid}"
        if sec_uid
        else f"https://www.douyin.com/user/{platform_account_id}"
    )
    return TikOmniResolvedCreator(
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
    creator: CreatorAccount,
    post: dict[str, Any],
    detail: dict[str, Any],
    statistics: dict[str, Any],
) -> ContentProfile:
    merged_sources = (statistics, detail, post)
    aweme_id = _extract_aweme_id(post) or _extract_aweme_id(detail) or _extract_aweme_id(statistics)
    if not aweme_id:
        raise CollectorParseError("TikOmni post is missing aweme_id")

    title = (
        _find_string(merged_sources, ("desc", "title", "caption", "share_title"))
        or f"{creator.nickname} content {aweme_id[-6:]}"
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
            "data_source": "tikomni_douyin",
            "list_item": post,
            "detail": detail or None,
            "statistics": statistics or None,
            "missing_metrics": missing,
        },
    )


def _map_tracked_content_profile(
    tracked_post: dict[str, Any],
    statistics: dict[str, Any],
) -> ContentProfile:
    like_count, like_present = _find_int_with_presence(
        statistics,
        ("digg_count", "like_count", "liked_count"),
    )
    comment_count, comment_present = _find_int_with_presence(
        statistics,
        ("comment_count", "comments_count"),
    )
    collect_count, collect_present = _find_int_with_presence(
        statistics,
        ("collect_count", "collects_count", "favorite_count", "favorites_count"),
    )
    share_count, share_present = _find_int_with_presence(
        statistics,
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
        platform_content_id=tracked_post["platform_content_id"],
        title=tracked_post["title"],
        summary=_dedupe_summary(tracked_post["title"], tracked_post.get("summary")),
        content_type=tracked_post["content_type"],
        content_url=tracked_post["content_url"],
        cover_url=tracked_post.get("cover_url"),
        published_at=tracked_post.get("published_at"),
        like_count=like_count if like_present else tracked_post["latest_like_count"],
        comment_count=(
            comment_count if comment_present else tracked_post["latest_comment_count"]
        ),
        collect_count=(
            collect_count if collect_present else tracked_post["latest_collect_count"]
        ),
        share_count=share_count if share_present else tracked_post["latest_share_count"],
        metrics_status="partial" if missing else "success",
        raw_data={
            "data_source": "tikomni_douyin",
            "tracking_refresh": True,
            "statistics": statistics or None,
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
                "latest_comment_count": int(
                    _get_attr(item, "latest_comment_count", 0) or 0
                ),
                "latest_collect_count": int(
                    _get_attr(item, "latest_collect_count", 0) or 0
                ),
                "latest_share_count": int(_get_attr(item, "latest_share_count", 0) or 0),
            }
        )
    return tracked_posts


def _get_attr(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _dedupe(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _to_decimal(value: float | Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _top_level_code(payload: dict[str, Any]) -> Any:
    for key in ("code", "status_code", "statusCode", "status"):
        if key in payload:
            return payload[key]
    return None


def _is_success_code(code: Any) -> bool:
    if isinstance(code, bool):
        return code
    if isinstance(code, int):
        return code in SUCCESS_CODES
    normalized = str(code).strip().lower()
    return normalized in SUCCESS_STRINGS


def _unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("data", "result", "aweme_detail", "aweme_info", "user"):
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
    return payload


def _sec_user_id_from_creator(creator: CreatorAccount) -> str | None:
    if creator.platform_account_id.startswith("MS4w"):
        return creator.platform_account_id
    profile_url = creator.profile_url or ""
    query_match = re.search(r"(?:sec_user_id|sec_uid|secUid)=([^&#\s]+)", profile_url)
    if query_match:
        return query_match.group(1)
    path = urlparse(profile_url).path
    path_match = re.search(r"/user/([^/?#\s]+)", path)
    if path_match and path_match.group(1).startswith("MS4w"):
        return path_match.group(1)
    return None


def _find_user_dict(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        for key in ("user", "user_info", "author"):
            value = data.get(key)
            if isinstance(value, dict):
                return value
        if any(key in data for key in ("nickname", "follower_count", "aweme_count")):
            return data
    for item in _walk_dicts(data):
        if any(key in item for key in ("nickname", "follower_count", "aweme_count")):
            return item
    return None


def _extract_post_dicts(data: Any) -> list[dict[str, Any]]:
    for key in ("aweme_list", "aweme_info", "aweme_detail", "items", "list", "videos"):
        value = _find_value(data, (key,))
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and _extract_aweme_id(data):
        return [data]
    return []


def _index_dicts_by_aweme_id(data: Any, aweme_ids: list[str]) -> dict[str, dict[str, Any]]:
    wanted = set(aweme_ids)
    indexed: dict[str, dict[str, Any]] = {}
    for item in _walk_dicts(data):
        aweme_id = _extract_aweme_id(item)
        if aweme_id and aweme_id in wanted:
            indexed[aweme_id] = item
    return indexed


def _extract_aweme_id(data: Any) -> str | None:
    return _find_string(data, ("aweme_id", "item_id", "video_id", "id"))


def _infer_content_type(data: Any) -> str:
    if _find_value(data, ("images", "image_infos", "image_list")):
        return "image"
    aweme_type = _find_int(data, ("aweme_type",), default=-1)
    if aweme_type in {68, 150}:
        return "image"
    return "video"


def _find_string(data: Any, keys: tuple[str, ...]) -> str | None:
    value = _find_value(data, keys)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, int | float):
        return str(value)
    return None


def _normalize_text_for_compare(value: str | None) -> str:
    return " ".join((value or "").split())


def _dedupe_summary(title: str, summary: str | None) -> str | None:
    if not summary:
        return None
    title_text = _normalize_text_for_compare(title)
    summary_text = _normalize_text_for_compare(summary)
    if not summary_text:
        return None
    if title_text and (
        title_text == summary_text
        or summary_text.startswith(title_text)
        or title_text.startswith(summary_text)
    ):
        return None
    return summary


def _find_int(data: Any, keys: tuple[str, ...], *, default: int = 0) -> int:
    value, present = _find_int_with_presence(data, keys)
    return value if present else default


def _find_int_with_presence(data: Any, keys: tuple[str, ...]) -> tuple[int, bool]:
    value = _find_value(data, keys)
    if value is None:
        return 0, False
    parsed = _parse_int(value)
    return (parsed or 0, parsed is not None)


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace(",", "")
    if not normalized:
        return None
    multiplier = 1
    if normalized.endswith(("w", "W", "万")):
        multiplier = 10_000
        normalized = normalized[:-1]
    elif normalized.endswith("亿"):
        multiplier = 100_000_000
        normalized = normalized[:-1]
    try:
        return int(float(normalized) * multiplier)
    except ValueError:
        digits = re.sub(r"[^\d.]", "", normalized)
        if not digits:
            return None
        try:
            return int(float(digits) * multiplier)
        except ValueError:
            return None


def _find_datetime(data: Any, keys: tuple[str, ...]) -> datetime | None:
    value = _find_value(data, keys)
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, int | float):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        parsed_int = _parse_int(stripped)
        if parsed_int and parsed_int > 1_000_000_000:
            return _find_datetime({"value": parsed_int}, ("value",))
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None
    return None


def _find_image_url(data: Any, keys: tuple[str, ...]) -> str | None:
    value = _find_value(data, keys)
    return _extract_url(value)


def _extract_url(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped.startswith(("http://", "https://")) else None
    if isinstance(value, list):
        for item in value:
            url = _extract_url(item)
            if url:
                return url
    if isinstance(value, dict):
        for key in ("url_list", "urls", "url", "uri", "cover", "display_image"):
            url = _extract_url(value.get(key))
            if url:
                return url
    return None


def _find_value(data: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(data, tuple):
        for item in data:
            value = _find_value(item, keys)
            if value is not None:
                return value
        return None
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        for value in data.values():
            result = _find_value(value, keys)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_value(item, keys)
            if result is not None:
                return result
    return None


def _walk_dicts(data: Any):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _walk_dicts(value)
    elif isinstance(data, list):
        for item in data:
            yield from _walk_dicts(item)
