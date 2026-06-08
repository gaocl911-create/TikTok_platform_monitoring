from types import SimpleNamespace
from urllib.error import HTTPError
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.collectors.base import CollectorValidationError, ContentProfile, CreatorProfile
from app.collectors.tikomni import (
    DOUYIN_ONE_VIDEO_WEB_ENDPOINT,
    DOUYIN_MULTI_STATISTICS_ENDPOINT,
    DOUYIN_MULTI_VIDEO_ENDPOINT,
    DOUYIN_SEC_USER_ID_ENDPOINT,
    DOUYIN_USER_POSTS_ENDPOINT,
    DOUYIN_WEB_PROFILE_ENDPOINT,
    TikOmniBudgetExceeded,
    TikOmniClient,
    TikOmniDouyinCollector,
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


def test_tikomni_client_adds_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(
            {
                "authorization": request.get_header("Authorization"),
                "content_type": request.get_header("Content-type"),
                "method": request.get_method(),
                "payload": request.data,
                "timeout": timeout,
            }
        )
        return FakeResponse(b'{"code": 200, "data": {"ok": true}}')

    monkeypatch.setattr("app.collectors.tikomni.urlopen", fake_urlopen)
    client = TikOmniClient(
        token="test-token",
        timeout_seconds=12,
        daily_budget_cny=20,
        estimated_unit_price_cny=0.008,
    )

    assert client.get("/api/test")["data"]["ok"] is True
    assert client.post("/api/test", ["7512345678901234567"])["data"]["ok"] is True
    assert captured[0] == {
        "authorization": "Bearer test-token",
        "content_type": None,
        "method": "GET",
        "payload": None,
        "timeout": 12,
    }
    assert captured[1] == {
        "authorization": "Bearer test-token",
        "content_type": "application/json",
        "method": "POST",
        "payload": b'["7512345678901234567"]',
        "timeout": 12,
    }
    assert client.usage_summary()["tikomni_request_count"] == 2


def test_tikomni_client_budget_limit_stops_before_http(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_urlopen(request, timeout):
        nonlocal called
        called = True
        return FakeResponse(b"{}")

    monkeypatch.setattr("app.collectors.tikomni.urlopen", fake_urlopen)
    client = TikOmniClient(
        token="test-token",
        daily_budget_cny=0.01,
        estimated_unit_price_cny=0.008,
        spent_today_cny=0.005,
    )

    with pytest.raises(TikOmniBudgetExceeded):
        client.get("/api/test")

    assert called is False
    assert client.usage_summary()["tikomni_budget_limited"] is True
    assert client.usage_summary()["tikomni_request_count"] == 0


def test_tikomni_client_explains_invalid_douyin_short_link() -> None:
    client = TikOmniClient(
        token="test-token",
        daily_budget_cny=20,
        estimated_unit_price_cny=0.008,
    )
    body = (
        b'{"code":400,"params":{"share_url":"https://v.douyin.com/JN_mUZfidzY/"},'
        b'"message":"Invalid request parameters"}'
    )
    error = HTTPError(
        url="https://api.tikomni.com/test",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=BytesIO(body),
    )

    with pytest.raises(CollectorValidationError, match="抖音短链无法被 TikOmni 识别"):
        client._raise_http_error(DOUYIN_ONE_VIDEO_WEB_ENDPOINT, error)


def test_tikomni_collector_maps_profile_and_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tikomni_enabled", True)
    monkeypatch.setattr(settings, "tikomni_api_token", "test-token")

    responses = {
        DOUYIN_SEC_USER_ID_ENDPOINT: {"code": 200, "data": {"sec_user_id": "MS4wLjABAAAA"}},
        DOUYIN_WEB_PROFILE_ENDPOINT: {
            "code": 200,
            "data": {
                "user": {
                    "nickname": "技术爬爬虾",
                    "signature": "分享计算机知识",
                    "ip_location": "山东",
                    "follower_count": 414000,
                    "following_count": 58,
                    "total_favorited": 2125000,
                    "aweme_count": 219,
                    "avatar_thumb": {"url_list": ["https://example.com/avatar.jpg"]},
                }
            },
        },
        DOUYIN_USER_POSTS_ENDPOINT: {
            "code": 200,
            "data": {
                "aweme_list": [
                    {
                        "aweme_id": "7512345678901234567",
                        "desc": "真实作品标题",
                        "create_time": 1717555200,
                        "video": {"cover": {"url_list": ["https://example.com/cover.jpg"]}},
                    }
                ]
            },
        },
        DOUYIN_MULTI_VIDEO_ENDPOINT: {
            "code": 200,
            "data": {
                "aweme_list": [
                    {
                        "aweme_id": "7512345678901234567",
                        "share_url": "https://www.douyin.com/video/7512345678901234567",
                    }
                ]
            },
        },
        DOUYIN_MULTI_STATISTICS_ENDPOINT: {
            "code": 200,
            "data": {
                "statistics_list": [
                    {
                        "aweme_id": "7512345678901234567",
                        "digg_count": 120,
                        "comment_count": 12,
                        "collect_count": 34,
                        "share_count": 5,
                    }
                ]
            },
        },
    }

    def fake_get(self, endpoint, params=None):
        return responses[endpoint]

    def fake_post(self, endpoint, payload=None):
        return responses[endpoint]

    monkeypatch.setattr(TikOmniClient, "get", fake_get)
    monkeypatch.setattr(TikOmniClient, "post", fake_post)

    creator = SimpleNamespace(
        id=1,
        platform="douyin",
        platform_account_id="40877664675",
        nickname="待采集账号",
        profile_url="https://v.douyin.com/example/",
        avatar_url=None,
        bio=None,
        verified_info=None,
        location=None,
        follower_count=0,
        following_count=0,
        total_like_count=0,
        content_count=0,
        monitor_interval_minutes=60,
        baseline_content_ids=["7510000000000000000"],
        known_content_ids=["7510000000000000000"],
    )

    collector = TikOmniDouyinCollector()
    profile = collector.fetch_creator_profile(creator)
    posts = collector.fetch_content_posts(creator)

    assert profile.nickname == "技术爬爬虾"
    assert profile.follower_count == 414000
    assert profile.following_count == 58
    assert profile.total_like_count == 2125000
    assert profile.content_count == 219
    assert posts[0].platform_content_id == "7512345678901234567"
    assert posts[0].like_count == 120
    assert posts[0].comment_count == 12
    assert posts[0].collect_count == 34
    assert posts[0].share_count == 5
    assert posts[0].metrics_status == "success"
    assert collector.content_status == "success"


def test_tikomni_collector_establishes_baseline_without_expensive_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "tikomni_enabled", True)
    monkeypatch.setattr(settings, "tikomni_api_token", "test-token")

    def fake_get(self, endpoint, params=None):
        assert endpoint == DOUYIN_USER_POSTS_ENDPOINT
        return {
            "code": 200,
            "data": {
                "aweme_list": [
                    {"aweme_id": "7512345678901234567", "desc": "old public post"}
                ]
            },
        }

    def fake_post(self, endpoint, payload=None):
        raise AssertionError("baseline creation must not fetch post detail/statistics")

    monkeypatch.setattr(TikOmniClient, "get", fake_get)
    monkeypatch.setattr(TikOmniClient, "post", fake_post)

    creator = SimpleNamespace(
        id=1,
        platform="douyin",
        platform_account_id="MS4wLjABAAAA",
        nickname="baseline account",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAA",
        avatar_url=None,
        bio=None,
        verified_info=None,
        location=None,
        follower_count=0,
        following_count=0,
        total_like_count=0,
        content_count=0,
        monitor_interval_minutes=60,
        baseline_content_ids=[],
        known_content_ids=[],
    )

    collector = TikOmniDouyinCollector()
    posts = collector.fetch_content_posts(creator)

    assert posts == []
    assert collector.content_status == "baseline_created"
    assert collector.baseline_created is True
    assert collector.last_seen_content_ids == ["7512345678901234567"]
    assert collector.new_content_ids == []


def test_tikomni_collector_skips_expensive_calls_when_no_new_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "tikomni_enabled", True)
    monkeypatch.setattr(settings, "tikomni_api_token", "test-token")

    def fake_get(self, endpoint, params=None):
        assert endpoint == DOUYIN_USER_POSTS_ENDPOINT
        return {
            "code": 200,
            "data": {
                "aweme_list": [
                    {"aweme_id": "7512345678901234567", "desc": "known public post"}
                ]
            },
        }

    def fake_post(self, endpoint, payload=None):
        raise AssertionError("no-new-content collection must not fetch post detail/statistics")

    monkeypatch.setattr(TikOmniClient, "get", fake_get)
    monkeypatch.setattr(TikOmniClient, "post", fake_post)

    creator = SimpleNamespace(
        id=1,
        platform="douyin",
        platform_account_id="MS4wLjABAAAA",
        nickname="known account",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAA",
        avatar_url=None,
        bio=None,
        verified_info=None,
        location=None,
        follower_count=0,
        following_count=0,
        total_like_count=0,
        content_count=0,
        monitor_interval_minutes=60,
        baseline_content_ids=[],
        known_content_ids=["7512345678901234567"],
    )

    collector = TikOmniDouyinCollector()
    posts = collector.fetch_content_posts(creator)

    assert posts == []
    assert collector.content_status == "no_new_content"
    assert collector.baseline_created is False
    assert collector.last_seen_content_ids == ["7512345678901234567"]
    assert collector.new_content_ids == []


def test_tikomni_collector_refreshes_tracked_content_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "tikomni_enabled", True)
    monkeypatch.setattr(settings, "tikomni_api_token", "test-token")

    def fake_get(self, endpoint, params=None):
        if endpoint == DOUYIN_USER_POSTS_ENDPOINT:
            return {
                "code": 200,
                "data": {
                    "aweme_list": [
                        {"aweme_id": "7512345678901234567", "desc": "known public post"}
                    ]
                },
            }
        assert endpoint == DOUYIN_MULTI_STATISTICS_ENDPOINT
        assert params == {"aweme_ids": "7512345678901234567"}
        return {
            "code": 200,
            "data": {
                "statistics_list": [
                    {
                        "aweme_id": "7512345678901234567",
                        "digg_count": 220,
                        "comment_count": 22,
                        "collect_count": 44,
                        "share_count": 8,
                    }
                ]
            },
        }

    def fake_post(self, endpoint, payload=None):
        raise AssertionError("tracked content metric refresh must not fetch post details")

    monkeypatch.setattr(TikOmniClient, "get", fake_get)
    monkeypatch.setattr(TikOmniClient, "post", fake_post)

    creator = SimpleNamespace(
        id=1,
        platform="douyin",
        platform_account_id="MS4wLjABAAAA",
        nickname="known account",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAA",
        avatar_url=None,
        bio=None,
        verified_info=None,
        location=None,
        follower_count=0,
        following_count=0,
        total_like_count=0,
        content_count=0,
        monitor_interval_minutes=30,
        baseline_content_ids=[],
        known_content_ids=["7512345678901234567"],
        tracked_content_posts=[
            SimpleNamespace(
                platform_content_id="7512345678901234567",
                title="tracked post",
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

    collector = TikOmniDouyinCollector()
    posts = collector.fetch_content_posts(creator)

    assert collector.content_status == "metrics_refreshed"
    assert collector.new_content_ids == []
    assert collector.refreshed_content_ids == ["7512345678901234567"]
    assert len(posts) == 1
    assert posts[0].platform_content_id == "7512345678901234567"
    assert posts[0].like_count == 220
    assert posts[0].comment_count == 22
    assert posts[0].collect_count == 44
    assert posts[0].share_count == 8
    assert posts[0].raw_data["tracking_refresh"] is True


def test_tikomni_single_content_only_refreshes_statistics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "tikomni_enabled", True)
    monkeypatch.setattr(settings, "tikomni_api_token", "test-token")
    called_endpoints = []

    def fake_get(self, endpoint, params=None):
        called_endpoints.append(endpoint)
        assert endpoint == DOUYIN_MULTI_STATISTICS_ENDPOINT
        assert params == {"aweme_ids": "7512345678901234567"}
        return {
            "code": 200,
            "data": {
                "statistics_list": [
                    {
                        "aweme_id": "7512345678901234567",
                        "digg_count": 220,
                        "comment_count": 22,
                        "collect_count": 44,
                        "share_count": 8,
                    }
                ]
            },
        }

    def fake_post(self, endpoint, payload=None):
        raise AssertionError("single-content refresh must not fetch post details")

    monkeypatch.setattr(TikOmniClient, "get", fake_get)
    monkeypatch.setattr(TikOmniClient, "post", fake_post)

    creator = SimpleNamespace(
        id=1,
        platform="douyin",
        platform_account_id="MS4wLjABAAAA",
        nickname="single work account",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAA",
        avatar_url=None,
        bio=None,
        verified_info=None,
        location=None,
        follower_count=0,
        following_count=0,
        total_like_count=0,
        content_count=0,
        monitor_interval_minutes=30,
        monitor_scope="single_content",
        baseline_content_ids=["7512345678901234567"],
        known_content_ids=["7512345678901234567"],
        tracked_content_posts=[
            SimpleNamespace(
                platform_content_id="7512345678901234567",
                title="tracked post",
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

    collector = TikOmniDouyinCollector()
    posts = collector.fetch_content_posts(creator)

    assert called_endpoints == [DOUYIN_MULTI_STATISTICS_ENDPOINT]
    assert collector.content_status == "metrics_refreshed"
    assert collector.refreshed_content_ids == ["7512345678901234567"]
    assert len(posts) == 1
    assert posts[0].like_count == 220


def test_tikomni_partial_metrics_still_create_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartialMetricsCollector:
        collector_type = "tikomni_douyin"
        version = "test-tikomni-v1"
        content_status = "partial"
        warnings = ["collect_count is missing"]

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="真实账号",
                avatar_url=None,
                bio="真实简介",
                verified_info=None,
                location="山东",
                follower_count=100,
                following_count=10,
                total_like_count=1000,
                content_count=1,
            )

        def fetch_content_posts(self, creator):
            return [
                ContentProfile(
                    platform_content_id="7512345678901234567",
                    title="部分指标作品",
                    summary=None,
                    content_type="video",
                    content_url="https://www.douyin.com/video/7512345678901234567",
                    cover_url=None,
                    published_at=None,
                    like_count=120,
                    comment_count=12,
                    collect_count=0,
                    share_count=5,
                    metrics_status="partial",
                )
            ]

        def usage_summary(self):
            return {
                "tikomni_request_count": 4,
                "tikomni_estimated_cost_cny": 0.032,
                "tikomni_endpoints": ["test"],
                "tikomni_budget_limited": False,
            }

    monkeypatch.setattr(
        "app.services.creators.get_collector",
        lambda creator: PartialMetricsCollector(),
    )
    payload = {
        "platform": "douyin",
        "platform_account_id": "tikomni-partial",
        "nickname": "待采集账号",
        "profile_url": "https://www.douyin.com/user/MS4wLjABAAAA",
        "group_name": "真实数据测试",
        "tags": ["真实数据"],
        "priority": "high",
        "monitor_interval_minutes": 60,
        "collector_type": "tikomni_douyin",
    }

    creator = client.post("/api/v1/creators", json=payload).json()
    response = client.post(f"/api/v1/creators/{creator['id']}/collect")

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["status"] == "partial"
    assert body["run"]["result_summary"]["tikomni_request_count"] == 4
    posts = client.get("/api/v1/posts", params={"creator_id": creator["id"]}).json()
    assert posts["total"] == 1
    assert posts["items"][0]["metrics_status"] == "partial"
    snapshots = client.get(f"/api/v1/posts/{posts['items'][0]['id']}/snapshots").json()
    assert len(snapshots) == 1
    assert snapshots[0]["like_count"] == 120


def test_creator_create_supports_tikomni_for_douyin_only(client: TestClient) -> None:
    payload = {
        "platform": "douyin",
        "platform_account_id": "tikomni-create",
        "nickname": "TikOmni账号",
        "profile_url": "https://www.douyin.com/user/MS4wLjABAAAA",
        "group_name": "真实数据测试",
        "tags": ["真实数据"],
        "priority": "high",
        "monitor_interval_minutes": 60,
        "collector_type": "tikomni_douyin",
    }
    assert client.post("/api/v1/creators", json=payload).status_code == 201

    invalid_payload = {
        **payload,
        "platform": "xiaohongshu",
        "platform_account_id": "xhs-tikomni-create",
        "profile_url": "https://www.xiaohongshu.com/user/profile/xhs-tikomni-create",
    }
    assert client.post("/api/v1/creators", json=invalid_payload).status_code == 422
