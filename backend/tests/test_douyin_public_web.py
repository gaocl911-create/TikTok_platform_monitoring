import subprocess

import pytest
from fastapi.testclient import TestClient

from app.collectors.base import (
    CollectorParseError,
    CollectorRenderError,
    CollectorTransientError,
    ContentProfile,
    CreatorProfile,
)
from app.collectors.douyin_public_web import (
    parse_compact_number,
    parse_douyin_content_html,
    parse_douyin_profile_html,
)

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

CONTENT_HTML = """
<html><body>
  <div data-e2e="user-post-list">
    <a href="/video/7512345678901234567" aria-label="账号自己的公开作品">
      <img src="https://example.com/cover.jpg" />
    </a>
  </div>
  <footer>
    <a href="/video/7599999999999999999">热门推荐，不属于该账号</a>
  </footer>
</body></html>
"""


def test_parse_compact_number() -> None:
    assert parse_compact_number("58") == 58
    assert parse_compact_number("41.4万") == 414_000
    assert parse_compact_number("1.2亿") == 120_000_000


def test_only_temporary_collector_errors_are_retryable() -> None:
    assert issubclass(CollectorRenderError, CollectorTransientError)
    assert not issubclass(CollectorParseError, CollectorTransientError)


def test_render_timeout_terminates_edge_process_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimedOutProcess:
        pid = 12345
        returncode = None

        def communicate(self, timeout):
            raise subprocess.TimeoutExpired(cmd="msedge", timeout=timeout)

    collector = __import__(
        "app.collectors.douyin_public_web",
        fromlist=["DouyinPublicWebCollector"],
    ).DouyinPublicWebCollector()
    process = TimedOutProcess()
    terminated: list[int] = []

    monkeypatch.setattr(collector, "_resolve_browser_path", lambda: "msedge.exe")
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        collector,
        "_terminate_process_tree",
        lambda item: terminated.append(item.pid),
    )

    with pytest.raises(CollectorRenderError, match="渲染超时"):
        collector._render_profile("https://v.douyin.com/example/")

    assert terminated == [12345]


def test_parse_douyin_public_profile() -> None:
    profile = parse_douyin_profile_html(PROFILE_HTML, "40877664675")

    assert profile.nickname == "技术爬爬虾"
    assert profile.follower_count == 414_000
    assert profile.following_count == 58
    assert profile.total_like_count == 2_125_000
    assert profile.content_count == 219
    assert profile.location == "山东"
    assert profile.bio == "分享好玩有趣的计算机知识与软件 DIY。"


def test_parse_douyin_content_only_accepts_account_post_list() -> None:
    posts = parse_douyin_content_html(CONTENT_HTML)

    assert len(posts) == 1
    assert posts[0].platform_content_id == "7512345678901234567"
    assert posts[0].title == "账号自己的公开作品"
    assert posts[0].cover_url == "https://example.com/cover.jpg"
    assert posts[0].published_at is None
    assert posts[0].metrics_status == "unavailable"


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


def test_real_public_post_without_metrics_has_no_fake_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartialContentCollector:
        collector_type = "douyin_public_web"
        version = "test-real-v2"
        content_status = "partial"
        warnings = ["公开作品未提供互动指标"]

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
            return [
                ContentProfile(
                    platform_content_id="7512345678901234567",
                    title="真实公开作品",
                    summary=None,
                    content_type="video",
                    content_url="https://www.douyin.com/video/7512345678901234567",
                    cover_url=None,
                    published_at=None,
                    like_count=0,
                    comment_count=0,
                    collect_count=0,
                    share_count=0,
                    metrics_status="unavailable",
                )
            ]

    monkeypatch.setattr(
        "app.services.creators.get_collector",
        lambda creator: PartialContentCollector(),
    )

    response = client.post(
        "/api/v1/creators",
        json={**REAL_CREATOR_PAYLOAD, "platform_account_id": "public-post-test"},
    )
    assert response.status_code == 201
    post = client.get("/api/v1/posts").json()["items"][0]
    assert post["metrics_status"] == "unavailable"
    assert post["published_at"] is None
    assert client.get(f"/api/v1/posts/{post['id']}/snapshots").json() == []


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
