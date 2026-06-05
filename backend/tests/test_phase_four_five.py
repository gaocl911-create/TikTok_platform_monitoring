import pytest
from fastapi.testclient import TestClient

from app.collectors.base import CollectorRenderError

CREATOR_PAYLOAD = {
    "platform": "douyin",
    "platform_account_id": "phase-four-five-failure",
    "nickname": "阶段四点五测试账号",
    "profile_url": "https://www.douyin.com/user/phase-four-five-failure",
    "group_name": "稳定性测试",
    "tags": ["稳定性"],
    "priority": "high",
    "monitor_interval_minutes": 30,
    "collector_type": "douyin_public_web",
}


def test_collection_runs_api_exposes_observability_fields(client: TestClient) -> None:
    payload = {
        **CREATOR_PAYLOAD,
        "platform_account_id": "phase-four-five-mock",
        "collector_type": "mock",
    }
    creator = client.post("/api/v1/creators", json=payload).json()
    client.post(f"/api/v1/creators/{creator['id']}/collect")

    response = client.get("/api/v1/collection-runs", params={"creator_id": creator["id"]})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["trigger_source"] == "manual"
    assert body["items"][0]["attempt"] == 1
    assert body["items"][0]["collector_type"] == "mock"
    assert body["items"][0]["duration_ms"] >= 0
    assert body["items"][0]["creator"]["nickname"] == creator["nickname"]


def test_manual_collection_rejects_concurrent_run_and_records_skip(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        **CREATOR_PAYLOAD,
        "platform_account_id": "phase-four-five-locked",
        "collector_type": "mock",
    }
    creator = client.post("/api/v1/creators", json=payload).json()
    monkeypatch.setattr("app.api.creators.acquire_creator_collection_lock", lambda creator_id: None)

    response = client.post(f"/api/v1/creators/{creator['id']}/collect")

    assert response.status_code == 409
    runs = client.get("/api/v1/collection-runs", params={"creator_id": creator["id"]}).json()
    assert runs["items"][0]["status"] == "skipped"
    assert runs["items"][0]["trigger_source"] == "manual"


def test_consecutive_collection_failures_create_system_alert(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingCollector:
        collector_type = "douyin_public_web"
        version = "test-failing-v1"
        content_status = "failed"
        warnings: list[str] = []

        def fetch_creator_profile(self, creator):
            raise CollectorRenderError("公开页面暂时无法渲染")

        def fetch_content_posts(self, creator):
            return []

    monkeypatch.setattr("app.services.creators.get_collector", lambda creator: FailingCollector())

    assert client.post("/api/v1/creators", json=CREATOR_PAYLOAD).status_code == 502
    creator = client.get("/api/v1/creators").json()["items"][0]
    first_retry = client.post(f"/api/v1/creators/{creator['id']}/collect")
    second_retry = client.post(f"/api/v1/creators/{creator['id']}/collect")
    assert first_retry.status_code == 202
    assert first_retry.json()["status"] == "queued"
    assert second_retry.status_code == 202

    alerts = client.get("/api/v1/alerts", params={"alert_type": "collection_failure"}).json()
    assert alerts["total"] == 1
    assert alerts["items"][0]["severity"] == "critical"
    assert "连续采集失败 3 次" in alerts["items"][0]["title"]

    runs = client.get(
        "/api/v1/collection-runs",
        params={"creator_id": creator["id"], "status": "failed"},
    ).json()
    assert runs["total"] == 3
    assert all(run["error_type"] == "CollectorRenderError" for run in runs["items"])
