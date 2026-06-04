from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.models.base import utc_now
from app.models.content_post import ContentPost
from app.models.content_snapshot import ContentSnapshot
from app.models.creator import CreatorAccount
from app.schemas.alert import AlertRuleCreate, AlertRuleUpdate
from app.services.notifications import send_alert_webhook

DEFAULT_ALERT_RULES = (
    {
        "name": "发现新内容",
        "alert_type": "new_content",
        "conditions_json": {},
        "notification_channels_json": ["webhook"],
    },
    {
        "name": "内容点赞增长",
        "alert_type": "content_like_growth",
        "conditions_json": {"threshold": 20},
        "notification_channels_json": ["webhook"],
    },
)


def ensure_default_alert_rules(db: Session) -> list[AlertRule]:
    existing_types = set(db.scalars(select(AlertRule.alert_type)).all())
    for rule_data in DEFAULT_ALERT_RULES:
        if rule_data["alert_type"] not in existing_types:
            db.add(AlertRule(**rule_data))
    db.flush()
    return list(db.scalars(select(AlertRule).where(AlertRule.is_enabled.is_(True))).all())


def evaluate_content_alerts(
    db: Session,
    creator: CreatorAccount,
    new_posts: list[ContentPost],
    snapshot_results: list[tuple[ContentPost, ContentSnapshot, int]],
) -> list[Alert]:
    rules = ensure_default_alert_rules(db)
    new_post_ids = {post.id for post in new_posts}
    alerts: list[Alert] = []

    for rule in rules:
        if rule.alert_type == "new_content":
            for post in new_posts:
                alerts.extend(
                    _create_alert_once(
                        db,
                        dedupe_key=f"new_content:{rule.id}:{post.id}",
                        creator=creator,
                        post=post,
                        rule=rule,
                        severity="info",
                        title=f"{creator.nickname} 发布了新内容",
                        message=post.title,
                    )
                )
        elif rule.alert_type == "content_like_growth":
            threshold = int(rule.conditions_json.get("threshold", 100))
            for post, snapshot, like_delta in snapshot_results:
                if post.id in new_post_ids or like_delta < threshold:
                    continue
                alerts.extend(
                    _create_alert_once(
                        db,
                        dedupe_key=f"content_like_growth:{rule.id}:{snapshot.id}",
                        creator=creator,
                        post=post,
                        rule=rule,
                        severity="warning",
                        title=f"{creator.nickname} 的内容点赞增长明显",
                        message=f"《{post.title}》本次采集新增 {like_delta} 个赞。",
                    )
                )
    return alerts


def _create_alert_once(
    db: Session,
    *,
    dedupe_key: str,
    creator: CreatorAccount,
    post: ContentPost,
    rule: AlertRule,
    severity: str,
    title: str,
    message: str,
) -> list[Alert]:
    exists = db.scalar(select(Alert.id).where(Alert.dedupe_key == dedupe_key))
    if exists:
        return []
    alert = Alert(
        creator_id=creator.id,
        content_id=post.id,
        rule_id=rule.id,
        dedupe_key=dedupe_key,
        alert_type=rule.alert_type,
        severity=severity,
        title=title,
        message=message,
    )
    db.add(alert)
    db.flush()
    return [alert]


def dispatch_alert_notifications(db: Session, alerts: list[Alert]) -> None:
    for alert in alerts:
        rule = db.get(AlertRule, alert.rule_id) if alert.rule_id else None
        channels = rule.notification_channels_json if rule else []
        if "webhook" not in channels:
            alert.notification_status = "skipped"
            alert.notification_error = None
        else:
            alert.notification_status, alert.notification_error = send_alert_webhook(alert)
    db.commit()


def list_alerts(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    alert_type: str | None = None,
) -> tuple[list[Alert], int, int]:
    filters = []
    if status:
        filters.append(Alert.status == status)
    if alert_type:
        filters.append(Alert.alert_type == alert_type)

    total = db.scalar(select(func.count(Alert.id)).where(*filters)) or 0
    unread_count = db.scalar(select(func.count(Alert.id)).where(Alert.status == "unread")) or 0
    query = (
        select(Alert)
        .where(*filters)
        .order_by(Alert.triggered_at.desc(), Alert.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(query).all()), total, unread_count


def mark_alert_read(db: Session, alert: Alert) -> Alert:
    alert.status = "read"
    alert.read_at = utc_now()
    db.commit()
    db.refresh(alert)
    return alert


def mark_all_alerts_read(db: Session) -> int:
    alerts = list(db.scalars(select(Alert).where(Alert.status == "unread")).all())
    now = utc_now()
    for alert in alerts:
        alert.status = "read"
        alert.read_at = now
    db.commit()
    return len(alerts)


def list_alert_rules(db: Session) -> list[AlertRule]:
    ensure_default_alert_rules(db)
    db.commit()
    return list(db.scalars(select(AlertRule).order_by(AlertRule.id)).all())


def create_alert_rule(db: Session, payload: AlertRuleCreate) -> AlertRule:
    rule = AlertRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_alert_rule(db: Session, rule: AlertRule, payload: AlertRuleUpdate) -> AlertRule:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule
