from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.collectors.base import ContentProfile, CreatorProfile
from app.core.database import get_db
from app.main import app
from app.models.content_post import ContentPost
from app.models.content_snapshot import ContentSnapshot
from app.services.creators import collect_creator, get_creator

CREATOR_PAYLOAD = {
    "platform": "douyin",
    "platform_account_id": "demo-account-001",
    "nickname": "示例创作者",
    "profile_url": "https://www.douyin.com/user/demo-account-001",
    "group_name": "竞品观察",
    "tags": ["美妆", "重点"],
    "priority": "high",
    "monitor_interval_minutes": 30,
}


def test_creator_monitoring_workflow(client: TestClient) -> None:
    create_response = client.post("/api/v1/creators", json=CREATOR_PAYLOAD)
    assert create_response.status_code == 201
    creator = create_response.json()
    assert creator["nickname"] == "示例创作者"
    assert creator["follower_count"] == 0
    assert creator["last_collected_at"] is None
    assert creator["next_collect_at"].endswith("Z")

    duplicate_response = client.post("/api/v1/creators", json=CREATOR_PAYLOAD)
    assert duplicate_response.status_code == 409

    list_response = client.get("/api/v1/creators", params={"platform": "douyin"})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    collect_response = client.post(f"/api/v1/creators/{creator['id']}/collect")
    assert collect_response.status_code == 200
    collected = collect_response.json()
    assert collected["run"]["status"] == "success"
    assert collected["creator"]["follower_count"] > creator["follower_count"]

    snapshots_response = client.get(f"/api/v1/creators/{creator['id']}/snapshots")
    assert snapshots_response.status_code == 200
    assert len(snapshots_response.json()) == 1
    assert snapshots_response.json()[-1]["captured_at"].endswith("Z")

    pause_response = client.patch(
        f"/api/v1/creators/{creator['id']}",
        json={"monitoring_status": "paused"},
    )
    assert pause_response.status_code == 200
    assert pause_response.json()["monitoring_status"] == "paused"

    delete_response = client.delete(f"/api/v1/creators/{creator['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/creators/{creator['id']}").status_code == 404


def test_profile_url_is_extracted_from_share_text(client: TestClient) -> None:
    payload = {
        **CREATOR_PAYLOAD,
        "platform_account_id": "share-text-account",
        "profile_url": "复制打开抖音 https://v.douyin.com/RPSHKjDnGoI/ 9@5.com :8pm",
    }

    response = client.post("/api/v1/creators", json=payload)

    assert response.status_code == 201
    assert response.json()["profile_url"] == "https://v.douyin.com/RPSHKjDnGoI/"


def test_douyin_short_url_is_extracted_when_share_suffix_follows(client: TestClient) -> None:
    payload = {
        **CREATOR_PAYLOAD,
        "platform_account_id": "share-suffix-account",
        "profile_url": "https://v.douyin.com/RPSHKjDnGoI/ 9@5.com :8pm",
    }

    response = client.post("/api/v1/creators", json=payload)

    assert response.status_code == 201
    assert response.json()["profile_url"] == "https://v.douyin.com/RPSHKjDnGoI/"


def test_regular_profile_url_with_spaces_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "spaced-profile-url",
            "profile_url": "https://www.douyin.com/user/contains space",
        },
    )

    assert response.status_code == 422


def test_profile_url_with_spaces_and_no_public_url_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "invalid-profile-url",
            "profile_url": "not a valid profile url",
        },
    )

    assert response.status_code == 422


def test_create_creator_queues_profile_only_initial_collection(
    client: TestClient,
    monkeypatch,
) -> None:
    queued = {}

    def fake_apply_async(*args, **kwargs):
        queued["args"] = args
        queued["kwargs"] = kwargs

        class Task:
            id = "profile-only-task"

        return Task()

    monkeypatch.setattr("app.api.creators.collect_creator_task.apply_async", fake_apply_async)

    response = client.post(
        "/api/v1/creators",
        json={**CREATOR_PAYLOAD, "platform_account_id": "profile-only-queued"},
    )

    assert response.status_code == 201
    assert queued["kwargs"]["countdown"] == 0
    assert queued["kwargs"]["args"][1] == "initial"
    assert queued["kwargs"]["args"][2] is False


def test_resolve_profile_endpoint_returns_prefill_payload(
    client: TestClient,
    monkeypatch,
) -> None:
    def fake_resolve_profile(db, *, platform: str, input_value: str):
        assert platform == "douyin"
        assert input_value == "https://v.douyin.com/example/"
        return {
            "platform": "douyin",
            "platform_account_id": "MS4wLjABAAAA",
            "platform_display_id": "34867887966",
            "nickname": "Resolved Creator",
            "profile_url": "https://www.douyin.com/user/MS4wLjABAAAA",
            "avatar_url": "https://example.com/avatar.jpg",
            "bio": "Profile bio",
            "verified_info": None,
            "location": "Shandong",
            "follower_count": 414000,
            "following_count": 58,
            "total_like_count": 2125000,
            "content_count": 219,
            "collector_type": "tikomni_douyin",
            "sec_user_id": "MS4wLjABAAAA",
            "warnings": [],
        }

    monkeypatch.setattr("app.api.creators.resolve_creator_profile", fake_resolve_profile)

    response = client.post(
        "/api/v1/creators/resolve-profile",
        json={"platform": "douyin", "input_value": "https://v.douyin.com/example/"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["nickname"] == "Resolved Creator"
    assert body["platform_display_id"] == "34867887966"
    assert body["follower_count"] == 414000
    assert body["collector_type"] == "tikomni_douyin"


def test_create_creator_persists_resolved_profile_without_queueing_initial_task(
    client: TestClient,
    monkeypatch,
) -> None:
    queued = False

    def fake_apply_async(*args, **kwargs):
        nonlocal queued
        queued = True

    monkeypatch.setattr("app.api.creators.collect_creator_task.apply_async", fake_apply_async)

    response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "MS4wLjABAAAA",
            "platform_display_id": "34867887966",
            "nickname": "Resolved Creator",
            "avatar_url": "https://example.com/avatar.jpg",
            "bio": "Profile bio",
            "location": "Shandong",
            "collector_type": "tikomni_douyin",
            "follower_count": 111576,
            "following_count": 500,
            "total_like_count": 4974858,
            "content_count": 94,
            "profile_resolved": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert queued is False
    assert body["platform_display_id"] == "34867887966"
    assert body["follower_count"] == 111576
    assert body["total_like_count"] == 4974858
    assert body["content_count"] == 94
    assert body["last_collected_at"].endswith("Z")
    assert body["data_quality_status"] == "partial"

    snapshots_response = client.get(f"/api/v1/creators/{body['id']}/snapshots")
    assert snapshots_response.status_code == 200
    snapshots = snapshots_response.json()
    assert len(snapshots) == 1
    assert snapshots[0]["follower_count"] == 111576


def test_profile_only_collection_skips_content_fetch(
    client: TestClient,
    monkeypatch,
) -> None:
    class ProfileOnlyCollector:
        collector_type = "douyin_public_web"
        version = "test-profile-only-v1"
        content_status = "success"
        warnings: list[str] = []

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="已识别作者",
                avatar_url=None,
                bio="主页简介",
                verified_info=None,
                location="山东",
                follower_count=1234,
                following_count=56,
                total_like_count=7890,
                content_count=12,
            )

        def fetch_content_posts(self, creator):
            raise AssertionError("profile-only collection must not fetch content posts")

    monkeypatch.setattr("app.services.creators.get_collector", lambda creator: ProfileOnlyCollector())
    create_response = client.post(
        "/api/v1/creators",
        json={**CREATOR_PAYLOAD, "platform_account_id": "profile-only-service"},
    )
    creator_id = create_response.json()["id"]

    override = app.dependency_overrides[get_db]
    db_gen = override()
    db = next(db_gen)
    try:
        creator = get_creator(db, creator_id)
        creator, snapshot, run = collect_creator(
            db,
            creator,
            trigger_source="initial",
            include_content=False,
        )
        post_count = db.scalar(
            select(func.count()).select_from(ContentPost).where(ContentPost.creator_id == creator_id)
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    assert creator.nickname == "已识别作者"
    assert creator.follower_count == 1234
    assert creator.total_like_count == 7890
    assert creator.content_count == 12
    assert creator.last_content_status == "pending"
    assert creator.data_quality_status == "partial"
    assert snapshot.follower_count == 1234
    assert run.status == "success"
    assert run.result_summary["collection_scope"] == "profile"
    assert run.result_summary["new_content_count"] == 0
    assert post_count == 0


def test_content_collection_establishes_baseline_without_importing_old_posts(
    client: TestClient,
    monkeypatch,
) -> None:
    class BaselineCollector:
        collector_type = "tikomni_douyin"
        version = "test-baseline-v1"
        content_status = "baseline_created"
        warnings = ["已建立作品基线，历史作品不会进入内容动态。"]
        last_seen_content_ids = ["old-aweme-1", "old-aweme-2"]
        new_content_ids: list[str] = []
        baseline_created = True

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="baseline creator",
                avatar_url=None,
                bio="profile bio",
                verified_info=None,
                location="Shandong",
                follower_count=100,
                following_count=5,
                total_like_count=1000,
                content_count=2,
            )

        def fetch_content_posts(self, creator):
            assert creator.known_content_ids == []
            return []

        def usage_summary(self):
            return {
                "tikomni_request_count": 2,
                "tikomni_estimated_cost_cny": 0.003,
                "tikomni_endpoints": ["profile", "list"],
                "tikomni_budget_limited": False,
            }

    monkeypatch.setattr("app.services.creators.get_collector", lambda creator: BaselineCollector())
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "baseline-service",
            "collector_type": "tikomni_douyin",
        },
    )
    creator_id = create_response.json()["id"]

    override = app.dependency_overrides[get_db]
    db_gen = override()
    db = next(db_gen)
    try:
        creator = get_creator(db, creator_id)
        creator, snapshot, run = collect_creator(
            db,
            creator,
            trigger_source="scheduled",
            include_content=True,
        )
        post_count = db.scalar(
            select(func.count()).select_from(ContentPost).where(ContentPost.creator_id == creator_id)
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    assert creator.baseline_content_ids == ["old-aweme-1", "old-aweme-2"]
    assert creator.content_baseline_established_at is not None
    assert creator.last_content_status == "baseline_created"
    assert creator.last_collection_error is None
    assert creator.data_quality_status == "verified"
    assert snapshot.data_quality_status == "verified"
    assert run.status == "success"
    assert run.result_summary["content_baseline_created"] is True
    assert run.result_summary["content_baseline_size"] == 2
    assert run.result_summary["new_content_count"] == 0
    assert run.result_summary["expensive_content_fetch_skipped"] is True
    assert post_count == 0


def test_content_collection_refreshes_tracked_post_snapshots(
    client: TestClient,
    monkeypatch,
) -> None:
    class MetricsRefreshCollector:
        collector_type = "tikomni_douyin"
        version = "test-metrics-refresh-v1"
        content_status = "metrics_refreshed"
        warnings: list[str] = []
        last_seen_content_ids = ["tracked-aweme"]
        new_content_ids: list[str] = []
        refreshed_content_ids = ["tracked-aweme"]
        baseline_created = False

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="metrics creator",
                avatar_url=None,
                bio="profile bio",
                verified_info=None,
                location="Shandong",
                follower_count=100,
                following_count=5,
                total_like_count=1000,
                content_count=1,
            )

        def fetch_content_posts(self, creator):
            assert creator.known_content_ids == ["tracked-aweme"]
            assert len(creator.tracked_content_posts) == 1
            assert creator.tracked_content_posts[0].platform_content_id == "tracked-aweme"
            return [
                ContentProfile(
                    platform_content_id="tracked-aweme",
                    title="Tracked work",
                    summary=None,
                    content_type="video",
                    content_url="https://www.douyin.com/video/tracked-aweme",
                    cover_url=None,
                    published_at=None,
                    like_count=25,
                    comment_count=3,
                    collect_count=4,
                    share_count=2,
                    metrics_status="success",
                    raw_data={"tracking_refresh": True},
                )
            ]

        def usage_summary(self):
            return {
                "tikomni_request_count": 2,
                "tikomni_estimated_cost_cny": 0.003,
                "tikomni_endpoints": ["profile", "statistics"],
                "tikomni_budget_limited": False,
            }

    monkeypatch.setattr(
        "app.services.creators.get_collector",
        lambda creator: MetricsRefreshCollector(),
    )
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "metrics-refresh-service",
            "collector_type": "tikomni_douyin",
        },
    )
    creator_id = create_response.json()["id"]

    override = app.dependency_overrides[get_db]
    db_gen = override()
    db = next(db_gen)
    try:
        db.add(
            ContentPost(
                creator_id=creator_id,
                platform_content_id="tracked-aweme",
                title="Tracked work",
                summary=None,
                content_type="video",
                content_url="https://www.douyin.com/video/tracked-aweme",
                cover_url=None,
                latest_like_count=10,
                latest_comment_count=1,
                latest_collect_count=2,
                latest_share_count=1,
                status="active",
                data_source="tikomni_douyin",
                metrics_status="success",
            )
        )
        db.commit()

        creator = get_creator(db, creator_id)
        creator, snapshot, run = collect_creator(
            db,
            creator,
            trigger_source="scheduled",
            include_content=True,
        )
        post = db.scalar(
            select(ContentPost).where(
                ContentPost.creator_id == creator_id,
                ContentPost.platform_content_id == "tracked-aweme",
            )
        )
        snapshot_count = db.scalar(
            select(func.count())
            .select_from(ContentSnapshot)
            .where(ContentSnapshot.content_id == post.id)
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    assert creator.last_content_status == "metrics_refreshed"
    assert creator.data_quality_status == "verified"
    assert run.status == "success"
    assert run.result_summary["new_content_count"] == 0
    assert run.result_summary["content_snapshot_count"] == 1
    assert run.result_summary["refreshed_content_count"] == 1
    assert post.latest_like_count == 25
    assert post.latest_comment_count == 3
    assert post.latest_collect_count == 4
    assert post.latest_share_count == 2
    assert snapshot_count == 1
