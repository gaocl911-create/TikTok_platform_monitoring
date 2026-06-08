from app.collectors.base import ContentProfile
from app.collectors.tikomni import TikOmniResolvedCreator, TikOmniResolvedWork


def _resolved_work() -> TikOmniResolvedWork:
    creator = TikOmniResolvedCreator(
        platform_account_id="MS4wLjABAAAA-work-author",
        platform_display_id="douyin-author",
        nickname="作品作者",
        profile_url="https://www.douyin.com/user/MS4wLjABAAAA-work-author",
        avatar_url="https://example.com/avatar.jpg",
        bio="作者简介",
        verified_info=None,
        location="山东",
        follower_count=100,
        following_count=10,
        total_like_count=1000,
        content_count=12,
    )
    content = ContentProfile(
        platform_content_id="7512345678901234567",
        title="单作品监控测试",
        summary="作品文案",
        content_type="video",
        content_url="https://www.douyin.com/video/7512345678901234567",
        cover_url="https://example.com/cover.jpg",
        published_at=None,
        like_count=120,
        comment_count=12,
        collect_count=30,
        share_count=5,
        metrics_status="success",
        raw_data={"tracking_mode": "single_work"},
    )
    return TikOmniResolvedWork(
        creator=creator,
        content=content,
        source_url="https://www.douyin.com/video/7512345678901234567",
        raw_data={"ok": True},
    )


class FakeWorkResolver:
    warnings: list[str] = []
    calls = 0

    def __init__(self, *args, **kwargs) -> None:
        return

    def resolve(self, input_value: str) -> TikOmniResolvedWork:
        type(self).calls += 1
        assert "douyin.com" in input_value
        return _resolved_work()

    def usage_summary(self):
        return {
            "tikomni_request_count": 1,
            "tikomni_estimated_cost_cny": 0.0015,
            "tikomni_endpoints": ["/api/u1/v1/douyin/app/v3/fetch_one_video_by_share_url"],
            "tikomni_budget_limited": False,
        }


def test_resolve_content_link_returns_work_preview(client, monkeypatch) -> None:
    FakeWorkResolver.calls = 0
    monkeypatch.setattr("app.services.posts.TikOmniDouyinWorkResolver", FakeWorkResolver)

    response = client.post(
        "/api/v1/posts/resolve-link",
        json={
            "platform": "douyin",
            "input_value": "https://www.douyin.com/video/7512345678901234567",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["creator"]["nickname"] == "作品作者"
    assert body["creator"]["platform_account_id"] == "MS4wLjABAAAA-work-author"
    assert body["content"]["platform_content_id"] == "7512345678901234567"
    assert body["content"]["like_count"] == 120
    assert body["resolve_token"]
    assert body["existing_creator_id"] is None
    assert body["existing_post_id"] is None


def test_resolve_content_link_matches_existing_creator_by_display_id(client, monkeypatch) -> None:
    FakeWorkResolver.calls = 0
    monkeypatch.setattr("app.services.posts.TikOmniDouyinWorkResolver", FakeWorkResolver)
    creator_response = client.post(
        "/api/v1/creators",
        json={
            "platform": "douyin",
            "platform_account_id": "older-sec-user-id",
            "platform_display_id": "douyin-author",
            "nickname": "已有作者",
            "profile_url": "https://www.douyin.com/user/older-sec-user-id",
            "tags": [],
            "priority": "normal",
            "monitor_interval_minutes": 30,
            "collector_type": "tikomni_douyin",
        },
    )
    assert creator_response.status_code == 201

    response = client.post(
        "/api/v1/posts/resolve-link",
        json={
            "platform": "douyin",
            "input_value": "https://www.douyin.com/video/7512345678901234567",
        },
    )

    assert response.status_code == 200
    assert response.json()["existing_creator_id"] == creator_response.json()["id"]


def test_add_content_link_reuses_resolve_token(client, monkeypatch) -> None:
    FakeWorkResolver.calls = 0
    monkeypatch.setattr("app.services.posts.TikOmniDouyinWorkResolver", FakeWorkResolver)
    resolve_response = client.post(
        "/api/v1/posts/resolve-link",
        json={
            "platform": "douyin",
            "input_value": "https://www.douyin.com/video/7512345678901234567",
        },
    )
    assert resolve_response.status_code == 200
    assert FakeWorkResolver.calls == 1

    add_response = client.post(
        "/api/v1/posts/from-link",
        json={
            "platform": "douyin",
            "input_value": "https://www.douyin.com/video/7512345678901234567",
            "resolve_token": resolve_response.json()["resolve_token"],
            "tags": ["兼职"],
            "monitor_interval_minutes": 30,
        },
    )

    assert add_response.status_code == 201
    assert FakeWorkResolver.calls == 1


def test_add_content_link_creates_single_work_creator_and_snapshot(client, monkeypatch) -> None:
    FakeWorkResolver.calls = 0
    monkeypatch.setattr("app.services.posts.TikOmniDouyinWorkResolver", FakeWorkResolver)

    response = client.post(
        "/api/v1/posts/from-link",
        json={
            "platform": "douyin",
            "input_value": "https://www.douyin.com/video/7512345678901234567",
            "group_name": "兼职单作品",
            "tags": ["兼职"],
            "monitor_interval_minutes": 30,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["creator_created"] is True
    assert body["post_created"] is True
    assert body["post"]["platform_content_id"] == "7512345678901234567"
    assert body["post"]["creator"]["nickname"] == "作品作者"
    assert body["post"]["latest_like_count"] == 120

    posts = client.get("/api/v1/posts").json()
    assert posts["total"] == 1
    post_id = posts["items"][0]["id"]
    snapshots = client.get(f"/api/v1/posts/{post_id}/snapshots").json()
    assert len(snapshots) == 1
    assert snapshots[0]["like_count"] == 120

    creators = client.get("/api/v1/creators").json()
    assert creators["total"] == 1
    creator = creators["items"][0]
    assert creator["monitor_scope"] == "single_content"
    assert creator["group_name"] == "兼职单作品"
    assert creator["tags"] == ["兼职"]
