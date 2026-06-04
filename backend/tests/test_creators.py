from fastapi.testclient import TestClient

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
    assert creator["follower_count"] > 0
    assert creator["last_collected_at"].endswith("Z")
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
    assert len(snapshots_response.json()) == 2
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
