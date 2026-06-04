from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import Alert
from app.models.alert_rule import AlertRule
from app.schemas.alert import (
    AlertListResponse,
    AlertRead,
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
)
from app.services.alerts import (
    create_alert_rule,
    list_alert_rules,
    list_alerts,
    mark_alert_read,
    mark_all_alerts_read,
    update_alert_rule,
)

router = APIRouter(tags=["alerts"])
DbSession = Annotated[Session, Depends(get_db)]


def require_alert(db: Session, alert_id: int) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预警不存在")
    return alert


def require_alert_rule(db: Session, rule_id: int) -> AlertRule:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预警规则不存在")
    return rule


@router.get("/alerts", response_model=AlertListResponse)
def list_alerts_endpoint(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    alert_type: str | None = None,
):
    items, total, unread_count = list_alerts(
        db,
        page=page,
        page_size=page_size,
        status=status_filter,
        alert_type=alert_type,
    )
    return AlertListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
    )


@router.patch("/alerts/read-all")
def mark_all_alerts_read_endpoint(db: DbSession) -> dict[str, int]:
    return {"updated": mark_all_alerts_read(db)}


@router.patch("/alerts/{alert_id}/read", response_model=AlertRead)
def mark_alert_read_endpoint(alert_id: int, db: DbSession):
    return mark_alert_read(db, require_alert(db, alert_id))


@router.get("/alert-rules", response_model=list[AlertRuleRead])
def list_alert_rules_endpoint(db: DbSession):
    return list_alert_rules(db)


@router.post("/alert-rules", response_model=AlertRuleRead, status_code=status.HTTP_201_CREATED)
def create_alert_rule_endpoint(payload: AlertRuleCreate, db: DbSession):
    return create_alert_rule(db, payload)


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleRead)
def update_alert_rule_endpoint(rule_id: int, payload: AlertRuleUpdate, db: DbSession):
    return update_alert_rule(db, require_alert_rule(db, rule_id), payload)
