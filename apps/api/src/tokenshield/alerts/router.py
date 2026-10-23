from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from tokenshield.alerts.models import Alert
from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.core.deps import SessionDep
from tokenshield.core.errors import NotFoundError
from tokenshield.core.schemas import ApiModel, Message

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertOut(ApiModel):
    id: int
    kind: str
    severity: str
    message: str
    acknowledged: bool
    created_at: datetime


class AlertList(ApiModel):
    items: list[AlertOut]
    unacknowledged: int


@router.get("", response_model=AlertList, summary="Budget and policy alerts")
async def list_alerts(
    _: Viewer,
    session: SessionDep,
    include_acknowledged: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> AlertList:
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if not include_acknowledged:
        stmt = stmt.where(Alert.acknowledged.is_(False))
    items = [AlertOut.model_validate(a) for a in (await session.scalars(stmt)).all()]
    open_count = await session.scalar(select(func.count()).where(Alert.acknowledged.is_(False)))
    return AlertList(items=items, unacknowledged=int(open_count or 0))


@router.post("/{alert_id}/ack", response_model=Message, summary="Acknowledge an alert")
async def ack(alert_id: int, _: Admin, session: SessionDep) -> Message:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise NotFoundError("Alert not found")
    alert.acknowledged = True
    await session.commit()
    return Message(message="Acknowledged")


@router.post("/ack-all", response_model=Message, summary="Acknowledge every open alert")
async def ack_all(_: Admin, session: SessionDep) -> Message:
    result = await session.execute(
        update(Alert).where(Alert.acknowledged.is_(False)).values(acknowledged=True)
    )
    await session.commit()
    return Message(message=f"Acknowledged {result.rowcount} alerts")  # type: ignore[attr-defined]
