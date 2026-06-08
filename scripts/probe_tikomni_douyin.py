from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://api.tikomni.com"


ENDPOINTS = {
    "sec_user_id": "/api/u1/v1/douyin/web/get_sec_user_id",
    "profile": "/api/u1/v1/douyin/web/handler_user_profile",
    "posts": "/api/u1/v1/douyin/app/v3/fetch_user_post_videos",
    "details": "/api/u1/v1/douyin/app/v3/fetch_multi_video",
    "statistics": "/api/u1/v1/douyin/app/v3/fetch_multi_video_statistics",
}


def load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_json(base_url: str, token: str, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    query = urlencode({key: value for key, value in params.items() if value is not None})
    if query:
        url = f"{url}?{query}"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "CreatorMonitorProbe/1.0",
        },
        method="GET",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, token: str, endpoint: str, payload: Any) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CreatorMonitorProbe/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("data", "result", "aweme_detail", "aweme_info", "user"):
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
    return payload


def find_value(data: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(data, dict):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        for value in data.values():
            result = find_value(value, keys)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_value(item, keys)
            if result is not None:
                return result
    return None


def collect_dicts(data: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(data, dict):
        items.append(data)
        for value in data.values():
            items.extend(collect_dicts(value))
    elif isinstance(data, list):
        for item in data:
            items.extend(collect_dicts(item))
    return items


def find_post_list(data: Any) -> list[dict[str, Any]]:
    for key in ("aweme_list", "items", "list", "videos"):
        value = find_value(data, (key,))
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def find_aweme_id(data: Any) -> str | None:
    value = find_value(data, ("aweme_id", "item_id", "video_id", "id"))
    return str(value) if value is not None else None


def detect_sec_user_id(profile_url: str) -> str | None:
    match = re.search(r"(?:sec_user_id|sec_uid|secUid)=([^&#\s]+)", profile_url)
    return match.group(1) if match else None


def summarize_keys(data: Any, *, limit: int = 40) -> list[str]:
    keys: list[str] = []
    for item in collect_dicts(data):
        for key in item.keys():
            if key not in keys:
                keys.append(key)
            if len(keys) >= limit:
                return keys
    return keys


def metric_report(data: Any) -> dict[str, Any]:
    metric_keys = {
        "like_count": ("digg_count", "like_count", "liked_count"),
        "comment_count": ("comment_count", "comments_count"),
        "collect_count": ("collect_count", "collects_count", "favorite_count", "favorites_count"),
        "share_count": ("share_count", "share_num", "shares_count"),
    }
    return {name: find_value(data, keys) for name, keys in metric_keys.items()}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Probe TikOmni Douyin field mapping without writing DB data.")
    parser.add_argument("--profile-url", required=True, help="Douyin profile URL or share URL")
    parser.add_argument("--limit", type=int, default=5, help="Maximum videos to inspect")
    parser.add_argument("--base-url", default=None, help="Override TikOmni API base URL")
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("TIKOMNI_API_TOKEN")
    if not token:
        raise SystemExit("TIKOMNI_API_TOKEN is missing. Add it to .env first.")
    base_url = args.base_url or os.getenv("TIKOMNI_API_BASE_URL") or DEFAULT_BASE_URL

    report: dict[str, Any] = {
        "base_url": base_url,
        "profile_url": args.profile_url,
        "endpoints": [],
    }

    sec_user_id = detect_sec_user_id(args.profile_url)
    if not sec_user_id:
        payload = request_json(base_url, token, ENDPOINTS["sec_user_id"], {"url": args.profile_url})
        report["endpoints"].append({"name": "get_sec_user_id", "keys": summarize_keys(payload)})
        sec_user_data = unwrap_data(payload)
        if isinstance(sec_user_data, str) and sec_user_data.startswith("MS4w"):
            sec_user_id = sec_user_data
        else:
            sec_user_id = find_value(
                sec_user_data,
                ("sec_user_id", "secUid", "sec_uid", "secUserId"),
            )
    if not sec_user_id:
        raise SystemExit("TikOmni response did not include sec_user_id.")
    report["sec_user_id"] = sec_user_id

    profile_payload = request_json(base_url, token, ENDPOINTS["profile"], {"sec_user_id": sec_user_id})
    profile_data = unwrap_data(profile_payload)
    report["endpoints"].append({"name": "handler_user_profile", "keys": summarize_keys(profile_payload)})
    report["profile_mapping"] = {
        "nickname": find_value(profile_data, ("nickname", "name")),
        "follower_count": find_value(profile_data, ("follower_count", "fans_count")),
        "following_count": find_value(profile_data, ("following_count", "follow_count")),
        "total_like_count": find_value(profile_data, ("total_favorited", "favorited_count", "like_count")),
        "content_count": find_value(profile_data, ("aweme_count", "video_count", "post_count")),
    }

    posts_payload = request_json(
        base_url,
        token,
        ENDPOINTS["posts"],
        {"sec_user_id": sec_user_id, "max_cursor": 0, "count": args.limit, "sort_type": 0},
    )
    posts_data = unwrap_data(posts_payload)
    posts = find_post_list(posts_data)[: args.limit]
    aweme_ids = [aweme_id for post in posts if (aweme_id := find_aweme_id(post))]
    report["endpoints"].append({"name": "fetch_user_post_videos", "keys": summarize_keys(posts_payload)})
    report["post_list_count"] = len(posts)
    report["sample_aweme_ids"] = aweme_ids
    report["post_list_metric_sample"] = [metric_report(post) for post in posts[:3]]

    if aweme_ids:
        joined_ids = ",".join(aweme_ids)
        detail_payload = post_json(base_url, token, ENDPOINTS["details"], aweme_ids[:10])
        stats_payload = request_json(base_url, token, ENDPOINTS["statistics"], {"aweme_ids": joined_ids})
        report["endpoints"].append({"name": "fetch_multi_video", "keys": summarize_keys(detail_payload)})
        report["endpoints"].append({"name": "fetch_multi_video_statistics", "keys": summarize_keys(stats_payload)})
        report["detail_metric_sample"] = metric_report(unwrap_data(detail_payload))
        report["statistics_metric_sample"] = metric_report(unwrap_data(stats_payload))

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
