"""Which budget counters apply to a request, and how to rebuild a counter from Postgres."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tokenshield.budgets.ledger import CounterSpec
from tokenshield.budgets.models import BudgetReservation
from tokenshield.budgets.windows import window_label, window_start, window_ttl_s
from tokenshield.gateway.catalog import BudgetInfo
from tokenshield.usage.models import ReconciliationEvent, UsageEvent


@dataclass(frozen=True, slots=True)
class Subject:
    """Who a request is attributed to, for budget matching."""

    project_id: uuid.UUID
    team_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    end_user: str | None
    model_alias: str


@dataclass(frozen=True, slots=True)
class AppliedBudget:
    budget: BudgetInfo
    counter: CounterSpec
    scope_value: str | None
    window_start: datetime | None


def _scope_value(b: BudgetInfo, s: Subject) -> str | None:
    """The attribution value this budget is keyed on, or None if it does not apply."""
    match b.scope_type:
        case "global":
            return "all"
        case "team":
            return str(s.team_id) if s.team_id and b.scope_id == str(s.team_id) else None
        case "project":
            return str(s.project_id) if b.scope_id == str(s.project_id) else None
        case "api_key":
            return str(s.api_key_id) if s.api_key_id and b.scope_id == str(s.api_key_id) else None
        case "end_user":
            if not s.end_user:
                return None
            # "*" means "each end user gets this budget separately".
            return s.end_user if b.scope_id in ("*", s.end_user) else None
        case "model":
            return s.model_alias if b.scope_id == s.model_alias else None
    return None


def counter_key(budget_id: uuid.UUID, period: str, now: datetime, scope_value: str) -> str:
    return f"ts:bud:{budget_id}:{window_label(period, now)}:{scope_value}"


def applicable(budgets: tuple[BudgetInfo, ...], s: Subject, now: datetime) -> list[AppliedBudget]:
    out: list[AppliedBudget] = []
    for b in budgets:
        value = _scope_value(b, s)
        if value is None:
            continue
        out.append(
            AppliedBudget(
                budget=b,
                counter=CounterSpec(
                    budget_id=str(b.id),
                    key=counter_key(b.id, b.period, now, value),
                    limit_nusd=b.limit_nusd,
                    hard=b.mode == "hard",
                    ttl_s=window_ttl_s(b.period, now),
                ),
                scope_value=value,
                window_start=window_start(b.period, now),
            )
        )
    return out


class CounterHydrator:
    """Rebuilds ``settled spend + outstanding reservations`` for one counter.

    Spend comes from the append-only usage ledger plus reconciliation corrections, so a
    budget created mid-month still counts the month's earlier traffic in its scope.
    """

    def __init__(self, sessionmaker: async_sessionmaker, applied: list[AppliedBudget]) -> None:  # type: ignore[type-arg]
        self._sessionmaker = sessionmaker
        self._by_key = {a.counter.key: a for a in applied}

    async def __call__(self, spec: CounterSpec) -> int:
        a = self._by_key[spec.key]
        conditions = []
        if a.window_start is not None:
            conditions.append(UsageEvent.created_at >= a.window_start)
        match a.budget.scope_type:
            case "team":
                conditions.append(UsageEvent.team_id == uuid.UUID(str(a.scope_value)))
            case "project":
                conditions.append(UsageEvent.project_id == uuid.UUID(str(a.scope_value)))
            case "api_key":
                conditions.append(UsageEvent.api_key_id == uuid.UUID(str(a.scope_value)))
            case "end_user":
                conditions.append(UsageEvent.end_user == a.scope_value)
            case "model":
                conditions.append(UsageEvent.model_alias == a.scope_value)
        async with self._sessionmaker() as session:
            spent = await session.scalar(
                select(func.coalesce(func.sum(UsageEvent.actual_cost_nusd), 0)).where(*conditions)
            )
            in_scope = select(UsageEvent.request_id).where(*conditions)
            corrections = await session.scalar(
                select(func.coalesce(func.sum(ReconciliationEvent.delta_cost_nusd), 0)).where(
                    ReconciliationEvent.request_id.in_(in_scope)
                )
            )
            outstanding = await session.scalar(
                select(func.coalesce(func.sum(BudgetReservation.amount_nusd), 0)).where(
                    BudgetReservation.counter_key == spec.key,
                    BudgetReservation.status.in_(("reserved", "uncertain")),
                )
            )
        return int(spent or 0) + int(corrections or 0) + int(outstanding or 0)
