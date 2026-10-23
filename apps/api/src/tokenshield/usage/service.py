"""Request log queries and report exports."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.audit.service import Actor, audit
from tokenshield.budgets.models import Budget, BudgetReservation
from tokenshield.core.errors import NotFoundError
from tokenshield.core.money import nusd_to_usd
from tokenshield.core.schemas import Page, decode_cursor, encode_cursor
from tokenshield.core.storage import ObjectStorage
from tokenshield.keys.models import ApiKey
from tokenshield.pricing.models import ModelPrice
from tokenshield.projects.models import Project
from tokenshield.usage.analytics import RANGES
from tokenshield.usage.models import Export, ReconciliationEvent, UsageEvent
from tokenshield.usage.schemas import (
    ExportDownload,
    ExportIn,
    ExportOut,
    ReconciliationOut,
    ReservationOut,
    UsageEventDetail,
    UsageEventOut,
)

EXPORT_COLUMNS = (
    "request_id",
    "created_at",
    "project",
    "api_key",
    "source",
    "end_user",
    "task_id",
    "endpoint",
    "model",
    "provider",
    "upstream_model",
    "status",
    "http_status",
    "cache_status",
    "rule",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "usage_source",
    "estimated_cost_usd",
    "actual_cost_usd",
    "avoided_cost_usd",
    "priced",
    "price_id",
    "latency_ms",
)


async def list_events(
    session: AsyncSession,
    *,
    cursor: str | None,
    limit: int,
    project_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    model: str | None = None,
    status: str | None = None,
    cache_status: str | None = None,
    end_user: str | None = None,
    task_id: str | None = None,
    q: str | None = None,
) -> Page[UsageEventOut]:
    """Keyset pagination on the primary key: constant cost at any depth."""
    stmt = (
        select(UsageEvent, Project.name, ApiKey.name)
        .outerjoin(Project, Project.id == UsageEvent.project_id)
        .outerjoin(ApiKey, ApiKey.id == UsageEvent.api_key_id)
        .order_by(UsageEvent.id.desc())
        .limit(limit + 1)
    )
    if (after := decode_cursor(cursor)) and after.isdigit():
        stmt = stmt.where(UsageEvent.id < int(after))
    filters = {
        UsageEvent.project_id: project_id,
        UsageEvent.api_key_id: api_key_id,
        UsageEvent.model_alias: model,
        UsageEvent.status: status,
        UsageEvent.cache_status: cache_status,
        UsageEvent.end_user: end_user,
        UsageEvent.task_id: task_id,
    }
    for column, value in filters.items():
        if value is not None:
            stmt = stmt.where(column == value)
    if q:
        stmt = stmt.where(UsageEvent.request_id.startswith(q.strip()))
    rows = (await session.execute(stmt)).all()
    items = [
        UsageEventOut.model_validate(e).model_copy(update={"project_name": p, "api_key_name": k})
        for e, p, k in rows[:limit]
    ]
    next_cursor = encode_cursor(rows[limit - 1][0].id) if len(rows) > limit else None
    return Page[UsageEventOut](items=items, next_cursor=next_cursor)


async def get_event(session: AsyncSession, request_id: str) -> UsageEventDetail:
    row = (
        await session.execute(
            select(UsageEvent, Project.name, ApiKey.name)
            .outerjoin(Project, Project.id == UsageEvent.project_id)
            .outerjoin(ApiKey, ApiKey.id == UsageEvent.api_key_id)
            .where(UsageEvent.request_id == request_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Request not found")
    event, project_name, key_name = row
    reservations = (
        await session.execute(
            select(BudgetReservation, Budget.name)
            .outerjoin(Budget, Budget.id == BudgetReservation.budget_id)
            .where(BudgetReservation.request_id == request_id)
            .order_by(BudgetReservation.id)
        )
    ).all()
    recon = (
        await session.scalars(
            select(ReconciliationEvent)
            .where(ReconciliationEvent.request_id == request_id)
            .order_by(ReconciliationEvent.id)
        )
    ).all()
    version = (
        await session.scalar(select(ModelPrice.version).where(ModelPrice.id == event.price_id))
        if event.price_id
        else None
    )
    return UsageEventDetail.model_validate(
        {
            **{k: getattr(event, k) for k in UsageEventOut.model_fields if hasattr(event, k)},
            "estimated_cost_nusd": event.estimated_cost_nusd,
            "actual_cost_nusd": event.actual_cost_nusd,
            "avoided_cost_nusd": event.avoided_cost_nusd,
            "project_name": project_name,
            "api_key_name": key_name,
            "reservations": [
                ReservationOut.model_validate(r).model_copy(update={"budget_name": name})
                for r, name in reservations
            ],
            "reconciliations": [ReconciliationOut.model_validate(r) for r in recon],
            "price_version": version,
        }
    )


async def create_export(
    session: AsyncSession, data: ExportIn, storage: ObjectStorage, actor: Actor
) -> ExportOut:
    since = datetime.now(UTC) - RANGES[data.range]
    stmt = (
        select(UsageEvent, Project.name, ApiKey.name)
        .outerjoin(Project, Project.id == UsageEvent.project_id)
        .outerjoin(ApiKey, ApiKey.id == UsageEvent.api_key_id)
        .where(UsageEvent.created_at >= since)
        .order_by(UsageEvent.id)
        .execution_options(yield_per=2000)
    )
    if data.project_id:
        stmt = stmt.where(UsageEvent.project_id == data.project_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    rows = 0
    async for e, project_name, key_name in await session.stream(stmt):
        writer.writerow(
            [
                e.request_id,
                e.created_at.isoformat(),
                project_name or "",
                key_name or "",
                e.source,
                _safe(e.end_user),
                _safe(e.task_id),
                e.endpoint,
                e.model_alias or "",
                e.provider or "",
                e.upstream_model or "",
                e.status,
                e.http_status,
                e.cache_status,
                e.rule or "",
                e.input_tokens,
                e.cached_input_tokens,
                e.output_tokens,
                e.usage_source,
                f"{nusd_to_usd(e.estimated_cost_nusd):.9f}",
                f"{nusd_to_usd(e.actual_cost_nusd):.9f}",
                f"{nusd_to_usd(e.avoided_cost_nusd):.9f}",
                e.priced,
                e.price_id or "",
                e.latency_ms,
            ]
        )
        rows += 1
    payload = buf.getvalue().encode()
    export_id = uuid.uuid4()
    key = f"exports/{datetime.now(UTC):%Y/%m}/{export_id}.csv"
    await storage.put(key, payload, "text/csv")
    export = Export(
        id=export_id,
        kind="usage_csv",
        params=data.model_dump(mode="json"),
        object_key=key,
        rows=rows,
        bytes=len(payload),
        created_by=actor.id,
    )
    session.add(export)
    audit(session, actor, "export.created", "export", export_id, rows=rows, range=data.range)
    await session.commit()
    await session.refresh(export)
    return ExportOut.model_validate(export)


def _safe(value: str | None) -> str:
    """Neutralise spreadsheet formula injection in caller-supplied fields."""
    if not value:
        return ""
    return "'" + value if value[0] in "=+-@\t\r" else value


async def list_exports(session: AsyncSession) -> list[ExportOut]:
    rows = await session.scalars(select(Export).order_by(Export.created_at.desc()).limit(50))
    return [ExportOut.model_validate(e) for e in rows.all()]


async def export_download(
    session: AsyncSession, export_id: uuid.UUID, storage: ObjectStorage
) -> tuple[ExportDownload, Export]:
    export = await session.get(Export, export_id)
    if export is None:
        raise NotFoundError("Export not found")
    filename = f"tokenshield-usage-{export.created_at:%Y%m%d-%H%M}.csv"
    return ExportDownload(
        url=await storage.download_url(export.object_key, filename), filename=filename
    ), export
