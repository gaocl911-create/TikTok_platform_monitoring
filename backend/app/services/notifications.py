import json
from urllib import request

from app.core.config import settings
from app.models.alert import Alert


def send_alert_webhook(alert: Alert) -> tuple[str, str | None]:
    if not settings.alert_webhook_url:
        return "skipped", None

    text = f"{alert.title}\n{alert.message}"
    if "open.feishu.cn" in settings.alert_webhook_url:
        payload = {"msg_type": "text", "content": {"text": text}}
    elif "qyapi.weixin.qq.com" in settings.alert_webhook_url:
        payload = {"msgtype": "text", "text": {"content": text}}
    else:
        payload = {"text": text, "alert_id": alert.id, "alert_type": alert.alert_type}

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    webhook_request = request.Request(
        settings.alert_webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(  # noqa: S310
            webhook_request,
            timeout=settings.alert_webhook_timeout_seconds,
        ) as response:
            if 200 <= response.status < 300:
                return "sent", None
            return "failed", f"Webhook HTTP {response.status}"
    except Exception as exc:
        return "failed", str(exc)
