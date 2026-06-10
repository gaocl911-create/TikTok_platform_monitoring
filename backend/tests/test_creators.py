from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.collectors.base import ContentProfile, CreatorProfile
from app.core.database import get_db
from app.main import app
from app.models.collection_run import CollectionRun
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
            "collector_type": "tikhub_douyin",
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
    assert body["collector_type"] == "tikhub_douyin"


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
            "collector_type": "tikhub_douyin",
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
    assert body["next_collect_at"] == body["last_collected_at"]
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
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "profile-only-service",
            "collector_type": "douyin_public_web",
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
    assert creator.next_collect_at == creator.last_collected_at
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
        collector_type = "tikhub_douyin"
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
                "tikhub_request_count": 2,
                "tikhub_estimated_cost_usd": 0.003,
                "tikhub_endpoints": ["profile", "list"],
                "tikhub_budget_limited": False,
            }

    monkeypatch.setattr("app.services.creators.get_collector", lambda creator: BaselineCollector())
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "baseline-service",
            "collector_type": "tikhub_douyin",
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


def test_creator_collection_imports_only_posts_after_baseline(
    client: TestClient,
    monkeypatch,
) -> None:
    stages = ["baseline", "new-post"]

    class AfterBaselineCollector:
        collector_type = "tikhub_douyin"
        version = "test-after-baseline-v1"
        content_status = "success"
        warnings: list[str] = []
        last_seen_content_ids: list[str] = []
        new_content_ids: list[str] = []
        refreshed_content_ids: list[str] = []
        baseline_created = False

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="after baseline creator",
                avatar_url=None,
                bio="profile bio",
                verified_info=None,
                location="Shandong",
                follower_count=100,
                following_count=5,
                total_like_count=1000,
                content_count=3,
            )

        def fetch_content_posts(self, creator):
            stage = stages.pop(0)
            if stage == "baseline":
                assert creator.monitor_scope == "creator_collection"
                assert creator.known_content_ids == []
                self.last_seen_content_ids = ["old-aweme-1", "old-aweme-2"]
                self.new_content_ids = []
                self.baseline_created = True
                self.content_status = "baseline_created"
                return []

            assert set(creator.known_content_ids) == {"old-aweme-1", "old-aweme-2"}
            self.last_seen_content_ids = ["new-aweme-1", "old-aweme-1", "old-aweme-2"]
            self.new_content_ids = ["new-aweme-1"]
            self.content_status = "success"
            return [
                ContentProfile(
                    platform_content_id="new-aweme-1",
                    title="new post after baseline",
                    summary=None,
                    content_type="video",
                    content_url="https://www.douyin.com/video/new-aweme-1",
                    cover_url=None,
                    published_at=None,
                    like_count=10,
                    comment_count=2,
                    collect_count=3,
                    share_count=1,
                    metrics_status="success",
                    raw_data={"stage": "after_baseline"},
                )
            ]

        def usage_summary(self):
            return {
                "tikhub_request_count": 2,
                "tikhub_estimated_cost_usd": 0.003,
                "tikhub_endpoints": ["profile", "list"],
                "tikhub_budget_limited": False,
            }

    monkeypatch.setattr("app.services.creators.get_collector", lambda creator: AfterBaselineCollector())
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "after-baseline-service",
            "collector_type": "tikhub_douyin",
        },
    )
    creator_id = create_response.json()["id"]

    override = app.dependency_overrides[get_db]
    db_gen = override()
    db = next(db_gen)
    try:
        creator = get_creator(db, creator_id)
        creator, _snapshot, first_run = collect_creator(
            db,
            creator,
            trigger_source="scheduled",
            include_content=True,
        )
        creator, _snapshot, second_run = collect_creator(
            db,
            creator,
            trigger_source="scheduled",
            include_content=True,
        )
        first_summary = first_run.result_summary
        second_summary = second_run.result_summary
        posts = db.scalars(
            select(ContentPost).where(ContentPost.creator_id == creator_id)
        ).all()
        post_ids = [post.platform_content_id for post in posts]
        baseline_ids = list(creator.baseline_content_ids or [])
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    assert first_summary["content_status"] == "baseline_created"
    assert first_summary["new_content_count"] == 0
    assert second_summary["content_status"] == "success"
    assert second_summary["new_content_count"] == 1
    assert post_ids == ["new-aweme-1"]
    assert set(baseline_ids) == {
        "new-aweme-1",
        "old-aweme-1",
        "old-aweme-2",
    }


def test_content_collection_refreshes_tracked_post_snapshots(
    client: TestClient,
    monkeypatch,
) -> None:
    class MetricsRefreshCollector:
        collector_type = "tikhub_douyin"
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
                "tikhub_request_count": 2,
                "tikhub_estimated_cost_usd": 0.003,
                "tikhub_endpoints": ["profile", "statistics"],
                "tikhub_budget_limited": False,
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
            "collector_type": "tikhub_douyin",
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
                data_source="tikhub_douyin",
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


def test_single_content_collection_skips_creator_profile_fetch(
    client: TestClient,
    monkeypatch,
) -> None:
    class SingleContentMetricsCollector:
        collector_type = "tikhub_douyin"
        version = "test-single-content-v1"
        content_status = "metrics_refreshed"
        warnings: list[str] = []
        last_seen_content_ids: list[str] = []
        new_content_ids: list[str] = []
        refreshed_content_ids = ["single-aweme"]
        baseline_created = False

        def fetch_creator_profile(self, creator):
            raise AssertionError("single-content collection must not fetch creator profile")

        def fetch_content_posts(self, creator):
            assert creator.monitor_scope == "single_content"
            assert creator.nickname == "single creator"
            assert len(creator.tracked_content_posts) == 1
            assert creator.tracked_content_posts[0].platform_content_id == "single-aweme"
            return [
                ContentProfile(
                    platform_content_id="single-aweme",
                    title="Single tracked work",
                    summary=None,
                    content_type="video",
                    content_url="https://www.douyin.com/video/single-aweme",
                    cover_url=None,
                    published_at=None,
                    like_count=45,
                    comment_count=6,
                    collect_count=7,
                    share_count=3,
                    metrics_status="success",
                    raw_data={"tracking_refresh": True},
                )
            ]

        def usage_summary(self):
            return {
                "tikhub_request_count": 1,
                "tikhub_estimated_cost_usd": 0.0375,
                "tikhub_endpoints": ["fetch_multi_video_statistics"],
                "tikhub_budget_limited": False,
            }

    monkeypatch.setattr(
        "app.services.creators.get_collector",
        lambda creator: SingleContentMetricsCollector(),
    )
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "single-content-service",
            "nickname": "single creator",
            "collector_type": "tikhub_douyin",
            "monitor_scope": "single_content",
            "follower_count": 99,
            "following_count": 8,
            "total_like_count": 777,
            "content_count": 2,
        },
    )
    creator_id = create_response.json()["id"]

    override = app.dependency_overrides[get_db]
    db_gen = override()
    db = next(db_gen)
    try:
        db.add(
            CollectionRun(
                creator_id=creator_id,
                status="success",
                trigger_source="scheduled",
                collector_type="tikhub_douyin",
                result_summary={
                    "collection_scope": "single_content_profile_and_metrics",
                    "creator_profile_fetch_skipped": False,
                    "content_list_fetch_skipped": True,
                },
            )
        )
        db.add(
            ContentPost(
                creator_id=creator_id,
                platform_content_id="single-aweme",
                title="Single tracked work",
                summary=None,
                content_type="video",
                content_url="https://www.douyin.com/video/single-aweme",
                cover_url=None,
                latest_like_count=30,
                latest_comment_count=4,
                latest_collect_count=5,
                latest_share_count=1,
                status="active",
                data_source="tikhub_douyin",
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
                ContentPost.platform_content_id == "single-aweme",
            )
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    assert creator.follower_count == 99
    assert creator.total_like_count == 777
    assert snapshot.follower_count == 99
    assert run.status == "success"
    assert run.result_summary["collection_scope"] == "single_content_metrics"
    assert run.result_summary["creator_profile_fetch_skipped"] is True
    assert run.result_summary["content_list_fetch_skipped"] is True
    assert run.result_summary["tikhub_request_count"] == 1
    assert run.result_summary["tikhub_endpoints"] == ["fetch_multi_video_statistics"]
    assert post.latest_like_count == 45
    assert post.latest_comment_count == 6
    assert post.latest_collect_count == 7
    assert post.latest_share_count == 3


def test_single_content_collection_fetches_missing_creator_profile(
    client: TestClient,
    monkeypatch,
) -> None:
    class SingleContentProfileCollector:
        collector_type = "tikhub_douyin"
        version = "test-single-content-profile-v1"
        content_status = "metrics_refreshed"
        warnings: list[str] = []
        last_seen_content_ids: list[str] = []
        new_content_ids: list[str] = []
        refreshed_content_ids = ["single-aweme-profile"]
        baseline_created = False

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="profile filled creator",
                avatar_url=None,
                bio="profile bio",
                verified_info=None,
                location="Shandong",
                follower_count=1234,
                following_count=12,
                total_like_count=8888,
                content_count=34,
            )

        def fetch_content_posts(self, creator):
            assert creator.monitor_scope == "single_content"
            assert creator.follower_count == 1234
            assert creator.content_count == 34
            assert len(creator.tracked_content_posts) == 1
            return [
                ContentProfile(
                    platform_content_id="single-aweme-profile",
                    title="Single tracked work with profile",
                    summary=None,
                    content_type="video",
                    content_url="https://www.douyin.com/video/single-aweme-profile",
                    cover_url=None,
                    published_at=None,
                    like_count=55,
                    comment_count=7,
                    collect_count=8,
                    share_count=4,
                    metrics_status="success",
                    raw_data={"tracking_refresh": True},
                )
            ]

        def usage_summary(self):
            return {
                "tikhub_request_count": 2,
                "tikhub_estimated_cost_usd": 0.039,
                "tikhub_endpoints": ["handler_user_profile", "fetch_multi_video_statistics"],
                "tikhub_budget_limited": False,
            }

    monkeypatch.setattr(
        "app.services.creators.get_collector",
        lambda creator: SingleContentProfileCollector(),
    )
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "single-content-missing-profile",
            "nickname": "missing profile creator",
            "collector_type": "tikhub_douyin",
            "monitor_scope": "single_content",
            "follower_count": 0,
            "following_count": 0,
            "total_like_count": 0,
            "content_count": 0,
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
                platform_content_id="single-aweme-profile",
                title="Single tracked work with profile",
                summary=None,
                content_type="video",
                content_url="https://www.douyin.com/video/single-aweme-profile",
                cover_url=None,
                latest_like_count=40,
                latest_comment_count=5,
                latest_collect_count=6,
                latest_share_count=2,
                status="active",
                data_source="tikhub_douyin",
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
                ContentPost.platform_content_id == "single-aweme-profile",
            )
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    assert creator.follower_count == 1234
    assert creator.content_count == 34
    assert creator.total_like_count == 8888
    assert snapshot.follower_count == 1234
    assert run.status == "success"
    assert run.result_summary["collection_scope"] == "single_content_profile_and_metrics"
    assert run.result_summary["creator_profile_fetch_skipped"] is False
    assert run.result_summary["content_list_fetch_skipped"] is True
    assert run.result_summary["tikhub_request_count"] == 2
    assert post.latest_like_count == 55
    assert post.latest_comment_count == 7
    assert post.latest_collect_count == 8
    assert post.latest_share_count == 4


def test_update_creator_rejects_tikhub_for_non_douyin(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform": "xiaohongshu",
            "platform_account_id": "xhs-tikhub-update",
            "profile_url": "https://www.xiaohongshu.com/user/profile/xhs-tikhub-update",
            "collector_type": "mock",
        },
    )
    assert create_response.status_code == 201

    response = client.patch(
        f"/api/v1/creators/{create_response.json()['id']}",
        json={"collector_type": "tikhub_douyin"},
    )

    assert response.status_code == 422
    assert "抖音真实采集器只能用于抖音账号" in response.json()["detail"]


def test_single_content_collection_refreshes_profile_when_interval_zero(
    client: TestClient,
    monkeypatch,
) -> None:
    class AlwaysRefreshProfileCollector:
        collector_type = "tikhub_douyin"
        version = "test-single-content-always-refresh-v1"
        content_status = "metrics_refreshed"
        warnings: list[str] = []
        last_seen_content_ids: list[str] = []
        new_content_ids: list[str] = []
        refreshed_content_ids = ["single-aweme-always-refresh"]
        baseline_created = False

        def fetch_creator_profile(self, creator):
            return CreatorProfile(
                nickname="always refreshed creator",
                avatar_url=None,
                bio="fresh profile bio",
                verified_info=None,
                location="Shandong",
                follower_count=4321,
                following_count=21,
                total_like_count=9999,
                content_count=56,
            )

        def fetch_content_posts(self, creator):
            assert creator.follower_count == 4321
            assert creator.content_count == 56
            return [
                ContentProfile(
                    platform_content_id="single-aweme-always-refresh",
                    title="Single tracked work always refresh",
                    summary=None,
                    content_type="video",
                    content_url="https://www.douyin.com/video/single-aweme-always-refresh",
                    cover_url=None,
                    published_at=None,
                    like_count=65,
                    comment_count=8,
                    collect_count=9,
                    share_count=5,
                    metrics_status="success",
                    raw_data={"tracking_refresh": True},
                )
            ]

        def usage_summary(self):
            return {
                "tikhub_request_count": 2,
                "tikhub_estimated_cost_usd": 0.039,
                "tikhub_endpoints": ["handler_user_profile", "fetch_multi_video_statistics"],
                "tikhub_budget_limited": False,
            }

    monkeypatch.setattr("app.services.creators.settings.single_content_profile_refresh_interval_hours", 0)
    monkeypatch.setattr(
        "app.services.creators.get_collector",
        lambda creator: AlwaysRefreshProfileCollector(),
    )
    create_response = client.post(
        "/api/v1/creators",
        json={
            **CREATOR_PAYLOAD,
            "platform_account_id": "single-content-always-refresh",
            "nickname": "existing profile creator",
            "collector_type": "tikhub_douyin",
            "monitor_scope": "single_content",
            "follower_count": 99,
            "following_count": 8,
            "total_like_count": 777,
            "content_count": 2,
        },
    )
    creator_id = create_response.json()["id"]

    override = app.dependency_overrides[get_db]
    db_gen = override()
    db = next(db_gen)
    try:
        db.add(
            CollectionRun(
                creator_id=creator_id,
                status="success",
                trigger_source="scheduled",
                collector_type="tikhub_douyin",
                result_summary={
                    "collection_scope": "single_content_profile_and_metrics",
                    "creator_profile_fetch_skipped": False,
                    "content_list_fetch_skipped": True,
                },
            )
        )
        db.add(
            ContentPost(
                creator_id=creator_id,
                platform_content_id="single-aweme-always-refresh",
                title="Single tracked work always refresh",
                summary=None,
                content_type="video",
                content_url="https://www.douyin.com/video/single-aweme-always-refresh",
                cover_url=None,
                latest_like_count=40,
                latest_comment_count=5,
                latest_collect_count=6,
                latest_share_count=2,
                status="active",
                data_source="tikhub_douyin",
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
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

    assert creator.follower_count == 4321
    assert creator.content_count == 56
    assert snapshot.follower_count == 4321
    assert run.status == "success"
    assert run.result_summary["collection_scope"] == "single_content_profile_and_metrics"
    assert run.result_summary["creator_profile_fetch_skipped"] is False
    assert run.result_summary["content_list_fetch_skipped"] is True
