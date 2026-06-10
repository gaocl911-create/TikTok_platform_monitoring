from types import SimpleNamespace
from datetime import datetime

import pytest

from app.collectors.tikhub import (
    TIKHUB_ONE_VIDEO_BY_SHARE_URL_ENDPOINT,
    TIKHUB_ONE_VIDEO_ENDPOINT,
    TikHubClient,
    TikHubDouyinCollector,
    TikHubDouyinWorkResolver,
)
from app.core.config import settings


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.payload


def test_tikhub_client_adds_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(
            {
                "authorization": request.get_header("Authorization"),
                "method": request.get_method(),
                "timeout": timeout,
            }
        )
        return FakeResponse(b'{"code": 200, "data": {"ok": true}}')

    monkeypatch.setattr("app.collectors.tikhub.urlopen", fake_urlopen)
    client = TikHubClient(
        token="test-token",
        timeout_seconds=9,
        daily_budget_usd=5,
        estimated_unit_price_usd=0.001,
    )

    assert client.get("/api/test")["data"]["ok"] is True
    assert captured == [
        {
            "authorization": "Bearer test-token",
            "method": "GET",
            "timeout": 9,
        }
    ]
    assert client.usage_summary()["tikhub_request_count"] == 1


def test_tikhub_work_resolver_maps_single_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tikhub_enabled", True)
    monkeypatch.setattr(settings, "tikhub_api_token", "test-token")

    def fake_get(self, endpoint, params=None):
        assert endpoint == TIKHUB_ONE_VIDEO_BY_SHARE_URL_ENDPOINT
        assert params["share_url"].startswith("https://www.douyin.com/video/")
        return _single_work_payload()

    monkeypatch.setattr(TikHubClient, "get", fake_get)

    resolver = TikHubDouyinWorkResolver()
    resolved = resolver.resolve("https://www.douyin.com/video/7512345678901234567")

    assert resolved.creator.platform_account_id == "MS4wLjABAAAA-author"
    assert resolved.creator.platform_display_id == "douyin-author"
    assert resolved.content.platform_content_id == "7512345678901234567"
    assert resolved.content.like_count == 120
    assert resolved.content.comment_count == 12
    assert resolved.content.collect_count == 34
    assert resolved.content.share_count == 5
    assert resolved.content.summary is None
    assert resolved.content.published_at == datetime(2024, 6, 5, 2, 40)
    assert resolved.content.metrics_status == "success"
    assert resolved.content.raw_data["data_source"] == "tikhub_douyin"


def test_tikhub_single_content_refresh_uses_one_video_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "tikhub_enabled", True)
    monkeypatch.setattr(settings, "tikhub_api_token", "test-token")
    calls = []

    def fake_get(self, endpoint, params=None):
        calls.append((endpoint, params))
        assert endpoint == TIKHUB_ONE_VIDEO_ENDPOINT
        assert params == {"aweme_id": "7512345678901234567"}
        return _single_work_payload(like_count=150)

    monkeypatch.setattr(TikHubClient, "get", fake_get)
    creator = SimpleNamespace(
        id=1,
        platform="douyin",
        platform_account_id="MS4wLjABAAAA-author",
        nickname="tracked creator",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAA-author",
        avatar_url=None,
        bio=None,
        verified_info=None,
        location=None,
        follower_count=100,
        following_count=10,
        total_like_count=1000,
        content_count=12,
        monitor_interval_minutes=30,
        monitor_scope="single_content",
        baseline_content_ids=["7512345678901234567"],
        known_content_ids=["7512345678901234567"],
        tracked_content_posts=[
            SimpleNamespace(
                platform_content_id="7512345678901234567",
                title="old title",
                summary=None,
                content_type="video",
                content_url="https://www.douyin.com/video/7512345678901234567",
                cover_url=None,
                published_at=None,
                latest_like_count=120,
                latest_comment_count=12,
                latest_collect_count=34,
                latest_share_count=5,
            )
        ],
    )

    collector = TikHubDouyinCollector()
    posts = collector.fetch_content_posts(creator)

    assert calls == [(TIKHUB_ONE_VIDEO_ENDPOINT, {"aweme_id": "7512345678901234567"})]
    assert collector.content_status == "metrics_refreshed"
    assert collector.refreshed_content_ids == ["7512345678901234567"]
    assert posts[0].like_count == 150
    assert posts[0].comment_count == 12
    assert posts[0].collect_count == 34
    assert posts[0].share_count == 5


def _single_work_payload(*, like_count: int = 120) -> dict:
    return {
        "code": 200,
        "data": {
            "aweme_detail": {
                "aweme_id": "7512345678901234567",
                "desc": "TikHub mapped work",
                "share_url": "https://www.douyin.com/video/7512345678901234567",
                "create_time": 1717555200,
                "statistics": {
                    "digg_count": like_count,
                    "comment_count": 12,
                    "collect_count": 34,
                    "share_count": 5,
                },
                "author": {
                    "sec_uid": "MS4wLjABAAAA-author",
                    "unique_id": "douyin-author",
                    "nickname": "TikHub author",
                    "follower_count": 100,
                    "following_count": 10,
                    "total_favorited": 1000,
                    "aweme_count": 12,
                },
            }
        },
    }
