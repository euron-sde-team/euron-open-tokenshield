"""Usage analytics over hourly rollups, plus raw events for the still-open hour.

Rollups make dashboard queries cost O(hours x dimensions) instead of O(requests). The open
hour is aggregated live so the dashboard is never more than a request behind. Responses are
cached in Redis for a few seconds because dashboards poll.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import orjson
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import Select, String, case, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.core.money import nusd_to_usd
from tokenshield.keys.models import ApiKey
from tokenshield.projects.models import Project
from tokenshield.usage.models import ReconciliationEvent, UsageEvent, UsageRollupHourly
from tokenshield.usage.schemas import BreakdownRow, Overview, SeriesPoint, TaskSummary, Totals

RANGES = {
    "1h": timedelta(hours=1),
    "24h": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}
CACHE_TTL_S = 10
NIL = uuid.UUID(int=0)


def _hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _unified(
    since: datetime, until: datetime, project_id: uuid.UUID | None, raw_from: datetime
) -> Any:
    """Rollups for hours the worker has closed, raw events after that, same columns.

    ``raw_from`` is the first hour not yet rolled up, so a lagging worker never leaves a
    gap: those hours are simply read raw until the worker catches up.
    """
    r = UsageRollupHourly
    roll = select(
        r.hour.label("hour"),
        r.project_id.label("project_id"),
        r.api_key_id.label("api_key_id"),
        r.model_alias.label("model_alias"),
        r.provider.label("provider"),
        r.status.label("status"),
        r.cache_status.label("cache_status"),
        r.requests.label("requests"),
        r.input_tokens.label("input_tokens"),
        r.cached_input_tokens.label("cached_input_tokens"),
        r.output_tokens.label("output_tokens"),
        r.cost_nusd.label("cost"),
        r.avoided_cost_nusd.label("avoided"),
        r.latency_ms_sum.label("latency"),
    ).where(r.hour >= _hour(since), r.hour < min(raw_from, until))
    e = UsageEvent
    rc = (
        select(
            ReconciliationEvent.request_id,
            func.sum(ReconciliationEvent.delta_cost_nusd).label("delta"),
        )
        .group_by(ReconciliationEvent.request_id)
        .subquery("rc")
    )
    raw_start = max(raw_from, since)
    raw = (
        select(
            func.date_trunc("hour", e.created_at).label("hour"),
            func.coalesce(e.project_id, NIL).label("project_id"),
            func.coalesce(e.api_key_id, NIL).label("api_key_id"),
            func.coalesce(e.model_alias, "").label("model_alias"),
            func.coalesce(e.provider, "").label("provider"),
            e.status.label("status"),
            e.cache_status.label("cache_status"),
            literal(1).label("requests"),
            e.input_tokens.label("input_tokens"),
            e.cached_input_tokens.label("cached_input_tokens"),
            e.output_tokens.label("output_tokens"),
            (e.actual_cost_nusd + func.coalesce(rc.c.delta, 0)).label("cost"),
            e.avoided_cost_nusd.label("avoided"),
            e.latency_ms.label("latency"),
        )
        .outerjoin(rc, rc.c.request_id == e.request_id)
        .where(e.created_at >= raw_start, e.created_at < until)
    )
    if project_id:
        roll = roll.where(r.project_id == project_id)
        raw = raw.where(e.project_id == project_id)
    return union_all(roll, raw).subquery("u")


def _totals_select(u: Any) -> Select[Any]:
    hit = u.c.cache_status.in_(("HIT", "SEMANTIC_HIT", "COALESCED"))
    return select(
        func.coalesce(func.sum(u.c.requests), 0),
        func.coalesce(func.sum(case((u.c.status == "SUCCESS", u.c.requests), else_=0)), 0),
        func.coalesce(func.sum(case((u.c.status == "REJECTED", u.c.requests), else_=0)), 0),
        func.coalesce(func.sum(case((u.c.status == "ERROR", u.c.requests), else_=0)), 0),
        func.coalesce(func.sum(case((u.c.status == "UNCERTAIN", u.c.requests), else_=0)), 0),
        func.coalesce(func.sum(case((hit, u.c.requests), else_=0)), 0),
        func.coalesce(func.sum(u.c.input_tokens), 0),
        func.coalesce(func.sum(u.c.cached_input_tokens), 0),
        func.coalesce(func.sum(u.c.output_tokens), 0),
        func.coalesce(func.sum(u.c.cost), 0),
        func.coalesce(func.sum(u.c.avoided), 0),
        func.coalesce(func.sum(case((u.c.status == "SUCCESS", u.c.latency), else_=0)), 0),
    )


async def raw_from(session: AsyncSession) -> datetime:
    last = await session.scalar(select(func.max(UsageRollupHourly.hour)))
    return last + timedelta(hours=1) if last else datetime(2000, 1, 1, tzinfo=UTC)


async def _totals(
    session: AsyncSession, since: datetime, until: datetime, project_id: uuid.UUID | None
) -> Totals:
    u = _unified(since, until, project_id, await raw_from(session))
    row = (await session.execute(_totals_select(u))).one()
    req, ok, rej, err, unc, hits, tin, tcin, tout, cost, avoided, lat = (int(v) for v in row)
    served = ok
    return Totals(
        requests=req,
        succeeded=ok,
        rejected=rej,
        errors=err,
        uncertain=unc,
        cache_hits=hits,
        input_tokens=tin,
        cached_input_tokens=tcin,
        output_tokens=tout,
        cost_usd=nusd_to_usd(cost),
        avoided_usd=nusd_to_usd(avoided),
        avg_latency_ms=round(lat / served, 1) if served else 0.0,
        cache_hit_rate=round(hits / served, 4) if served else 0.0,
    )


class Analytics:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis

    async def _cached(self, key: str, compute: Any) -> Any:
        try:
            hit = await self.redis.get(f"ts:an:{key}")
            if hit:
                return orjson.loads(hit)
        except RedisError:
            pass
        value = await compute()
        data = orjson.loads(orjson.dumps(value, default=lambda o: o.model_dump(mode="json")))
        with contextlib.suppress(RedisError):
            await self.redis.set(f"ts:an:{key}", orjson.dumps(data), ex=CACHE_TTL_S)
        return data

    async def overview(self, range_: str, project_id: uuid.UUID | None) -> Overview:
        async def compute() -> Overview:
            now = datetime.now(UTC)
            span = RANGES[range_]
            return Overview(
                range=range_,
                since=now - span,
                totals=await _totals(self.session, now - span, now, project_id),
                previous=await _totals(self.session, now - 2 * span, now - span, project_id),
            )

        return Overview.model_validate(await self._cached(f"ov:{range_}:{project_id}", compute))

    async def timeseries(self, range_: str, project_id: uuid.UUID | None) -> list[SeriesPoint]:
        async def compute() -> list[SeriesPoint]:
            now = datetime.now(UTC)
            span = RANGES[range_]
            u = _unified(now - span, now, project_id, await raw_from(self.session))
            bucket = u.c.hour if span <= timedelta(days=2) else func.date_trunc("day", u.c.hour)
            hit = u.c.cache_status.in_(("HIT", "SEMANTIC_HIT", "COALESCED"))
            rows = (
                await self.session.execute(
                    select(
                        bucket.label("t"),
                        func.sum(u.c.requests),
                        func.sum(u.c.cost),
                        func.sum(u.c.avoided),
                        func.sum(u.c.input_tokens),
                        func.sum(u.c.output_tokens),
                        func.sum(case((u.c.status == "REJECTED", u.c.requests), else_=0)),
                        func.sum(case((hit, u.c.requests), else_=0)),
                    )
                    .group_by("t")
                    .order_by("t")
                )
            ).all()
            by_t = {r[0]: r for r in rows}
            step = timedelta(hours=1) if span <= timedelta(days=2) else timedelta(days=1)
            start = (
                _hour(now - span)
                if step == timedelta(hours=1)
                else (now - span).replace(hour=0, minute=0, second=0, microsecond=0)
            )
            points, t = [], start
            while t <= now:
                r = by_t.get(t)
                points.append(
                    SeriesPoint(
                        t=t,
                        requests=int(r[1]) if r else 0,
                        cost_usd=nusd_to_usd(int(r[2])) if r else 0,
                        avoided_usd=nusd_to_usd(int(r[3])) if r else 0,
                        input_tokens=int(r[4]) if r else 0,
                        output_tokens=int(r[5]) if r else 0,
                        rejected=int(r[6]) if r else 0,
                        cache_hits=int(r[7]) if r else 0,
                    )
                )
                t += step
            return points

        data = await self._cached(f"ts:{range_}:{project_id}", compute)
        return [SeriesPoint.model_validate(p) for p in data]

    async def breakdown(
        self, range_: str, by: str, project_id: uuid.UUID | None
    ) -> list[BreakdownRow]:
        async def compute() -> list[BreakdownRow]:
            now = datetime.now(UTC)
            u = _unified(now - RANGES[range_], now, project_id, await raw_from(self.session))
            col = {
                "model": u.c.model_alias,
                "provider": u.c.provider,
                "project": cast(u.c.project_id, String),
                "api_key": cast(u.c.api_key_id, String),
                "status": u.c.status,
                "cache_status": u.c.cache_status,
            }[by]
            rows = (
                await self.session.execute(
                    select(
                        col.label("k"),
                        func.sum(u.c.requests),
                        func.sum(u.c.cost),
                        func.sum(u.c.avoided),
                        func.sum(u.c.input_tokens),
                        func.sum(u.c.output_tokens),
                    )
                    .group_by("k")
                    .order_by(func.sum(u.c.cost).desc(), func.sum(u.c.requests).desc())
                    .limit(25)
                )
            ).all()
            labels = await self._labels(by, [str(r[0]) for r in rows])
            total_cost = sum(int(r[2]) for r in rows) or 0
            total_req = sum(int(r[1]) for r in rows) or 1
            return [
                BreakdownRow(
                    key=str(r[0]),
                    label=labels.get(str(r[0]), str(r[0]) or "unattributed"),
                    requests=int(r[1]),
                    cost_usd=nusd_to_usd(int(r[2])),
                    avoided_usd=nusd_to_usd(int(r[3])),
                    input_tokens=int(r[4]),
                    output_tokens=int(r[5]),
                    share=round(
                        (int(r[2]) / total_cost) if total_cost else int(r[1]) / total_req, 4
                    ),
                )
                for r in rows
            ]

        data = await self._cached(f"bd:{range_}:{by}:{project_id}", compute)
        return [BreakdownRow.model_validate(p) for p in data]

    async def _labels(self, by: str, keys: list[str]) -> dict[str, str]:
        ids = []
        for k in keys:
            try:
                ids.append(uuid.UUID(k))
            except ValueError:
                continue
        labels = {str(NIL): "playground" if by == "api_key" else "unattributed"}
        if by == "project" and ids:
            for i, name in (
                await self.session.execute(
                    select(Project.id, Project.name).where(Project.id.in_(ids))
                )
            ).all():
                labels[str(i)] = name
        if by == "api_key" and ids:
            for i, name in (
                await self.session.execute(select(ApiKey.id, ApiKey.name).where(ApiKey.id.in_(ids)))
            ).all():
                labels[str(i)] = name
        return labels

    async def tasks(
        self, range_: str, project_id: uuid.UUID | None, limit: int = 50
    ) -> list[TaskSummary]:
        e = UsageEvent
        since = datetime.now(UTC) - RANGES[range_]
        stmt = (
            select(
                e.task_id,
                Project.name,
                func.count(),
                func.sum(e.actual_cost_nusd),
                func.sum(case((e.status == "REJECTED", 1), else_=0)),
                func.min(e.created_at),
                func.max(e.created_at),
                func.max(case((e.status == "REJECTED", e.rule), else_=None)),
            )
            .outerjoin(Project, Project.id == e.project_id)
            .where(e.task_id.is_not(None), e.created_at >= since)
            .group_by(e.task_id, Project.name)
            .order_by(func.max(e.created_at).desc())
            .limit(limit)
        )
        if project_id:
            stmt = stmt.where(e.project_id == project_id)
        return [
            TaskSummary(
                task_id=r[0],
                project_name=r[1],
                calls=int(r[2]),
                cost_usd=nusd_to_usd(int(r[3] or 0)),
                rejected=int(r[4]),
                first_at=r[5],
                last_at=r[6],
                last_rule=r[7],
            )
            for r in (await self.session.execute(stmt)).all()
        ]
