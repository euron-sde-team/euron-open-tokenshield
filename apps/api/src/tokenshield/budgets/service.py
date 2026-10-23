"""Budget administration and live status."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tokenshield.audit.service import Actor, audit
from tokenshield.budgets.ledger import BudgetLedger, CounterSpec
from tokenshield.budgets.models import Budget
from tokenshield.budgets.resolver import AppliedBudget, CounterHydrator, counter_key
from tokenshield.budgets.schemas import BudgetIn, BudgetOut, BudgetUpdate
from tokenshield.budgets.windows import window_end, window_start, window_ttl_s
from tokenshield.core.errors import AppError, NotFoundError
from tokenshield.core.money import nusd_to_usd, usd_to_nusd
from tokenshield.gateway.catalog import BudgetInfo
from tokenshield.keys.models import ApiKey
from tokenshield.projects.models import Project
from tokenshield.providers.models import Model
from tokenshield.teams.models import Team


def _info(b: Budget) -> BudgetInfo:
    return BudgetInfo(
        id=b.id,
        name=b.name,
        scope_type=b.scope_type,
        scope_id=b.scope_id,
        period=b.period,
        limit_nusd=b.limit_nusd,
        mode=b.mode,
        alert_threshold_pct=b.alert_threshold_pct,
    )


def _out(b: Budget, label: str | None) -> BudgetOut:
    now = datetime.now(UTC)
    return BudgetOut(
        id=b.id,
        name=b.name,
        scope_type=b.scope_type,
        scope_id=b.scope_id,
        scope_label=label,
        period=b.period,
        limit_usd=nusd_to_usd(b.limit_nusd),
        mode=b.mode,
        alert_threshold_pct=b.alert_threshold_pct,
        enabled=b.enabled,
        created_at=b.created_at,
        window_start=window_start(b.period, now),
        window_end=window_end(b.period, now),
    )


async def _labels(session: AsyncSession, budgets: list[Budget]) -> dict[str, str]:
    ids = {
        b.scope_id for b in budgets if b.scope_type in ("team", "project", "api_key") and b.scope_id
    }
    uuids = []
    for i in ids:
        try:
            uuids.append(uuid.UUID(i))
        except ValueError:
            continue
    labels: dict[str, str] = {}
    if uuids:
        for model, column in ((Team, Team.name), (Project, Project.name), (ApiKey, ApiKey.name)):
            for row in (
                await session.execute(select(model.id, column).where(model.id.in_(uuids)))
            ).all():
                labels[str(row[0])] = str(row[1])
    for b in budgets:
        if b.scope_type == "global":
            labels.setdefault("", "Whole gateway")
        elif b.scope_type == "end_user" and b.scope_id == "*":
            labels["*"] = "Each end user"
    return labels


async def list_budgets(
    session: AsyncSession,
    ledger: BudgetLedger,
    sessionmaker: async_sessionmaker,  # type: ignore[type-arg]
) -> list[BudgetOut]:
    budgets = list((await session.scalars(select(Budget).order_by(Budget.created_at))).all())
    labels = await _labels(session, budgets)
    now = datetime.now(UTC)
    outs: list[BudgetOut] = []
    measurable: list[tuple[int, AppliedBudget]] = []
    for b in budgets:
        out = _out(b, labels.get(b.scope_id or "", b.scope_id))
        outs.append(out)
        # Per-user "*" budgets have one counter per user; there is no single figure to show.
        if b.scope_type == "end_user" and b.scope_id == "*":
            continue
        scope_value = "all" if b.scope_type == "global" else str(b.scope_id)
        spec = CounterSpec(
            str(b.id),
            counter_key(b.id, b.period, now, scope_value),
            b.limit_nusd,
            b.mode == "hard",
            window_ttl_s(b.period, now),
        )
        measurable.append(
            (len(outs) - 1, AppliedBudget(_info(b), spec, scope_value, window_start(b.period, now)))
        )
    if not measurable:
        return outs
    try:
        values = await ledger.current([a.counter.key for _, a in measurable])
    except RedisError:
        return outs
    hydrate = CounterHydrator(sessionmaker, [a for _, a in measurable])
    for (idx, applied), value in zip(measurable, values, strict=True):
        spent = value if value is not None else await hydrate(applied.counter)
        outs[idx].spent_usd = nusd_to_usd(spent)
        outs[idx].used_pct = round(spent * 100 / max(1, applied.budget.limit_nusd), 1)
    return outs


async def _validate_scope(session: AsyncSession, data: BudgetIn) -> None:
    lookup = {"team": Team, "project": Project, "api_key": ApiKey}
    if data.scope_type in lookup:
        try:
            target = await session.get(lookup[data.scope_type], uuid.UUID(str(data.scope_id)))
        except ValueError:
            target = None
        if target is None:
            raise AppError(
                f"No {data.scope_type.replace('_', ' ')} with that id", code="unknown_scope"
            )
    elif data.scope_type == "model" and not await session.scalar(
        select(Model.id).where(Model.alias == data.scope_id)
    ):
        raise AppError("No model with that alias", code="unknown_scope")


async def create_budget(session: AsyncSession, data: BudgetIn, actor: Actor) -> BudgetOut:
    await _validate_scope(session, data)
    budget = Budget(
        name=data.name,
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        period=data.period,
        limit_nusd=usd_to_nusd(data.limit_usd),
        mode=data.mode,
        alert_threshold_pct=data.alert_threshold_pct,
        enabled=data.enabled,
    )
    session.add(budget)
    await session.flush()
    await session.refresh(budget)
    audit(
        session,
        actor,
        "budget.created",
        "budget",
        budget.id,
        name=budget.name,
        scope=f"{budget.scope_type}:{budget.scope_id}",
        limit_usd=str(data.limit_usd),
        mode=budget.mode,
    )
    await session.commit()
    return _out(budget, None)


async def update_budget(
    session: AsyncSession, budget_id: uuid.UUID, data: BudgetUpdate, actor: Actor
) -> BudgetOut:
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise NotFoundError("Budget not found")
    changes = data.model_dump(exclude_unset=True)
    if "limit_usd" in changes:
        budget.limit_nusd = usd_to_nusd(changes.pop("limit_usd"))
        changes["limit_nusd"] = budget.limit_nusd
    for field, value in changes.items():
        setattr(budget, field, value)
    audit(
        session,
        actor,
        "budget.updated",
        "budget",
        budget.id,
        **{k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return _out(budget, None)


async def delete_budget(session: AsyncSession, budget_id: uuid.UUID, actor: Actor) -> None:
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise NotFoundError("Budget not found")
    audit(session, actor, "budget.deleted", "budget", budget.id, name=budget.name)
    await session.delete(budget)
    await session.commit()
