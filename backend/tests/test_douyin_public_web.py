import pytest
from fastapi.testclient import TestClient

from app.collectors.base import CollectorRenderError, CreatorProfile
from app.collectors.douyin_public_web import parse_compact_number, parse_douyin_profile_html

REAL_CREATOR_PAYLOAD = {
    "platform": "douyin",
    "platform_account_id": "40877664675",
    "nickname": "待采集账号",
    "profile_url": "https://v.douyin.com/example/",
    "group_name": "真实数据测试",
    "tags": ["真实数据"],
    "priority": "high",
    "monitor_interval_minutes": 60,
    "collector_type": "douyin_public_web",
}

PROFILE_HTML = """
<html>
  <head><title>技术爬爬虾的抖音 - 抖音</title></head>
  <body>
    <section data-e2e="user-info">
      <h1>技术爬爬虾</h1>
      <div data-e2e="user-info-follow"><span>关注</span><strong>58</strong></div>
      <div data-e2e="user-info-fans"><span>粉丝</span><strong>41.4万</strong></div>
      <div data-e2e="user-info-like"><span>获赞</span><strong>212.5万</strong></div>
      <p>抖音号：40877664675</p>
      <p>IP属地：山东</p>
      <p>分享好玩有趣的计算机知识与软件 DIY。</p>
    </section>
    <span data-e2e="user-tab-count">219</span>
    <div data-e2e="user-post-list">服务异常，重新刷新拉取数据</div>
  </body>
</html>
"""


def test_parse_compact_number() -> None:
    assert parse_compact_number("58") == 58
    assert parse_compact_number("41.4万") == 414_000
    assert parse_compact_number("1.2亿") == 120_000_000


def test_parse_douyin_public_profile() -> None:
    profile = parse_douyin_profile_html(PROFILE_HTML, "40877664675")

    assert profile.nickname == "技术爬爬虾"
    assert profile.follower_count == 414_000
    assert profile.following_count == 58
    assert profile.total_like_count == 2_125_000
    assert profile.content_count == 219
    assert profile.location == "山东"
    assert profile.bio == "分享好玩有趣的计算机知识与软件 DIY。"


def test_real_collection_partial_status_never_adds_mock_posts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartialCollector:
        collector_type = "douyin_public_web"
        version = "test-real-v1"
        content_status = "unavailable"
        warnings = ["作品明细暂不可用"]

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="技术爬爬虾",
                avatar_url=None,
                bio="真实公开简介",
                verified_info=None,
                location="山东",
                follower_count=414_000,
                following_count=58,
                total_like_count=2_125_000,
                content_count=219,
            )

        def fetch_content_posts(self, creator):
            return []

    monkeypatch.setattr("app.services.creators.get_collector", lambda creator: PartialCollector())

    create_response = client.post("/api/v1/creators", json=REAL_CREATOR_PAYLOAD)
    assert create_response.status_code == 201
    creator = create_response.json()
    assert creator["follower_count"] == 414_000
    assert creator["data_quality_status"] == "partial"
    assert creator["collector_type"] == "douyin_public_web"
    assert creator["last_content_status"] == "unavailable"

    posts = client.get("/api/v1/posts", params={"creator_id": creator["id"]}).json()
    assert posts["total"] == 0
    snapshots = client.get(f"/api/v1/creators/{creator['id']}/snapshots").json()
    assert snapshots[0]["collector_type"] == "douyin_public_web"
    assert snapshots[0]["data_quality_status"] == "partial"

    collect_response = client.post(f"/api/v1/creators/{creator['id']}/collect")
    assert collect_response.status_code == 200
    assert collect_response.json()["run"]["status"] == "partial"


def test_real_collection_failure_is_recorded_without_mock_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingCollector:
        collector_type = "douyin_public_web"
        version = "test-real-v1"
        content_status = "failed"
        warnings: list[str] = []

        def fetch_creator_profile(self, creator):
            raise CollectorRenderError("公开主页需要人工验证")

        def fetch_content_posts(self, creator):
            return []

    monkeypatch.setattr("app.services.creators.get_collector", lambda creator: FailingCollector())

    create_response = client.post("/api/v1/creators", json=REAL_CREATOR_PAYLOAD)
    assert create_response.status_code == 502

    items = client.get("/api/v1/creators").json()["items"]
    assert len(items) == 1
    assert items[0]["follower_count"] == 0
    assert items[0]["data_quality_status"] == "failed"
    assert items[0]["last_content_status"] == "failed"
    assert "人工验证" in items[0]["last_collection_error"]


def test_switching_from_mock_to_real_removes_current_mock_data(client: TestClient) -> None:
    payload = {
        **REAL_CREATOR_PAYLOAD,
        "platform_account_id": "switch-source-test",
        "profile_url": "https://www.douyin.com/user/switch-source-test",
        "collector_type": "mock",
    }
    created = client.post("/api/v1/creators", json=payload).json()
    assert created["follower_count"] > 0
    assert client.get("/api/v1/posts", params={"creator_id": created["id"]}).json()["total"] == 3

    updated = client.patch(
        f"/api/v1/creators/{created['id']}",
        json={"collector_type": "douyin_public_web"},
    ).json()

    assert updated["data_quality_status"] == "pending"
    assert updated["follower_count"] == 0
    assert updated["total_like_count"] == 0
    assert updated["last_collected_at"] is None
    assert client.get("/api/v1/posts", params={"creator_id": created["id"]}).json()["total"] == 0

    snapshots = client.get(f"/api/v1/creators/{created['id']}/snapshots").json()
    assert snapshots[0]["collector_type"] == "mock"
