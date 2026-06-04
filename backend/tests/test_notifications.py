from app.core.config import settings
from app.models.alert import Alert
from app.services.notifications import send_alert_webhook


class SuccessfulResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_generic_webhook_notification(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alert_webhook_url", "https://example.com/alerts")
    monkeypatch.setattr(
        "app.services.notifications.request.urlopen",
        lambda *args, **kwargs: SuccessfulResponse(),
    )
    alert = Alert(
        creator_id=1,
        dedupe_key="test:1",
        alert_type="new_content",
        severity="info",
        title="发现新内容",
        message="测试通知",
    )

    status, error = send_alert_webhook(alert)

    assert status == "sent"
    assert error is None
