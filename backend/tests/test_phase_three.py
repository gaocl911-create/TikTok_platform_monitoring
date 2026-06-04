from fastapi.testclient import TestClient

CREATOR_PAYLOAD = {
    "platform": "xiaohongshu",
    "platform_account_id": "phase-three-demo",
    "nickname": "阶段三测试账号",
    "profile_url": "https://www.xiaohongshu.com/user/profile/phase-three-demo",
    "group_name": "阶段三",
    "tags": ["动态", "预警"],
    "priority": "high",
    "monitor_interval_minutes": 30,
}


def test_content_discovery_snapshot_and_alert_workflow(client: TestClient) -> None:
    create_response = client.post("/api/v1/creators", json=CREATOR_PAYLOAD)
    assert create_response.status_code == 201
    creator = create_response.json()

    first_posts_response = client.get("/api/v1/posts", params={"creator_id": creator["id"]})
    assert first_posts_response.status_code == 200
    first_posts = first_posts_response.json()
    assert first_posts["total"] == 3
    assert len({post["platform_content_id"] for post in first_posts["items"]}) == 3
    assert first_posts["items"][0]["published_at"].endswith("Z")

    first_post = first_posts["items"][0]
    snapshots_response = client.get(f"/api/v1/posts/{first_post['id']}/snapshots")
    assert snapshots_response.status_code == 200
    assert len(snapshots_response.json()) == 1

    collect_response = client.post(f"/api/v1/creators/{creator['id']}/collect")
    assert collect_response.status_code == 200
    summary = collect_response.json()["run"]["result_summary"]
    assert summary["new_content_count"] == 1
    assert summary["alert_count"] >= 1

    second_posts = client.get("/api/v1/posts", params={"creator_id": creator["id"]}).json()
    assert second_posts["total"] == 4
    assert len({post["platform_content_id"] for post in second_posts["items"]}) == 4

    repeated_snapshots = client.get(f"/api/v1/posts/{first_post['id']}/snapshots").json()
    assert len(repeated_snapshots) == 2

    alerts_response = client.get("/api/v1/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert alerts["total"] >= 4
    assert alerts["unread_count"] == alerts["total"]
    assert all(alert["notification_status"] == "skipped" for alert in alerts["items"])
    assert alerts["items"][0]["triggered_at"].endswith("Z")

    read_response = client.patch(f"/api/v1/alerts/{alerts['items'][0]['id']}/read")
    assert read_response.status_code == 200
    assert read_response.json()["status"] == "read"

    read_all_response = client.patch("/api/v1/alerts/read-all")
    assert read_all_response.status_code == 200
    assert client.get("/api/v1/alerts").json()["unread_count"] == 0

    rules_response = client.get("/api/v1/alert-rules")
    assert rules_response.status_code == 200
    rules = rules_response.json()
    assert {rule["alert_type"] for rule in rules} == {"new_content", "content_like_growth"}

    growth_rule = next(rule for rule in rules if rule["alert_type"] == "content_like_growth")
    update_rule_response = client.patch(
        f"/api/v1/alert-rules/{growth_rule['id']}",
        json={"conditions_json": {"threshold": 100}},
    )
    assert update_rule_response.status_code == 200
    assert update_rule_response.json()["conditions_json"]["threshold"] == 100
