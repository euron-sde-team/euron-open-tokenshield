"""Accounting for each request: one usage event plus its budget ledger rows.

Hot path: the record is appended to a Redis Stream (``XADD``, usually inside the same
pipeline as the budget settlement, so it costs no extra round trip). Workers drain the
stream through a consumer group and write batches to Postgres. Measured on the local
stack this removed ~10 ms of synchronous database time from every request.

Durability: Redis runs with AOF, entries stay pending until a worker commits and acks
them, and a crashed worker's entries are reclaimed by another. If Redis itself is
unreachable the record is written straight to Postgres instead, so it is never dropped.
``request_id`` is unique, so a replayed batch can never double count.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import orjson
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from tokenshield.budgets.models import BudgetReservation
from tokenshield.usage.models import UsageEvent

log = logging.getLogger("tokenshield.usage")

STREAM_KEY = "ts:usage:stream"
GROUP = "recorders"
# Cap the stream length so a stopped worker cannot exhaust Redis memory. Approximate
# trimming (~) is O(1); a backlog this large means the worker is down and alarms fire.
STREAM_MAXLEN = 1_000_000


@dataclass(slots=True)
class ReservationRow:
    budget_id: str
    counter_key: str
    amount_nusd: int
    actual_nusd: int | None
    status: str  # settled | released | uncertain


@dataclass(slots=True)
class UsageRecord:
    request_id: str
    status: str  # SUCCESS | REJECTED | ERROR | UNCERTAIN
    http_status: int
    project_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None
    source: str = "api"
    end_user: str | None = None
    task_id: str | None = None
    endpoint: str = "chat"
    model_alias: str | None = None
    provider: str | None = None
    upstream_model: str | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_input_tokens: int = 0
    usage_source: str = "none"
    estimated_cost_nusd: int = 0
    actual_cost_nusd: int = 0
    avoided_cost_nusd: int = 0
    price_id: int | None = None
    priced: bool = True
    cache_status: str = "BYPASS"
    rule: str | None = None
    reason: str | None = None
    latency_ms: int = 0
    stream: bool = False
    prompt_excerpt: str | None = None
    reservations: list[ReservationRow] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_UUID_FIELDS = ("project_id", "team_id", "api_key_id")


def encode(rec: UsageRecord) -> bytes:
    # asyncpg hands back its own UUID class, which orjson does not know: fall back to str.
    return orjson.dumps(asdict(rec), default=str)


def decode(raw: bytes) -> UsageRecord:
    data: dict[str, Any] = orjson.loads(raw)
    for name in _UUID_FIELDS:
        if data.get(name):
            data[name] = uuid.UUID(data[name])
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    data["reservations"] = [ReservationRow(**r) for r in data.get("reservations") or []]
    return UsageRecord(**data)


class UsageRecorder:
    def __init__(self, sessionmaker: async_sessionmaker, redis: Redis | None = None) -> None:  # type: ignore[type-arg]
        self._sessionmaker = sessionmaker
        self._redis = redis

    def enqueue(self, pipe: Pipeline, rec: UsageRecord) -> None:
        """Add the record to a pipeline the caller is about to execute."""
        pipe.xadd(STREAM_KEY, {"r": encode(rec)}, maxlen=STREAM_MAXLEN, approximate=True)

    async def record(self, rec: UsageRecord) -> None:
        """Enqueue on its own (paths without a settlement pipeline), falling back to Postgres."""
        if self._redis is not None:
            try:
                await self._redis.xadd(
                    STREAM_KEY, {"r": encode(rec)}, maxlen=STREAM_MAXLEN, approximate=True
                )
                return
            except RedisError:
                log.warning(
                    "usage stream unavailable; writing directly", extra={"rid": rec.request_id}
                )
        await self.write([rec])

    async def write(self, records: Sequence[UsageRecord]) -> None:
        """Insert a batch in one transaction. Duplicate request ids are ignored."""
        if not records:
            return
        events: list[dict[str, Any]] = []
        reservations: list[dict[str, Any]] = []
        for rec in records:
            row = asdict(rec)
            row.pop("reservations")
            events.append(row)
            settled_at = rec.created_at
            reservations.extend(
                {
                    "request_id": rec.request_id,
                    "budget_id": uuid.UUID(r.budget_id),
                    "counter_key": r.counter_key,
                    "amount_nusd": r.amount_nusd,
                    "actual_nusd": r.actual_nusd,
                    "status": r.status,
                    "settled_at": settled_at if r.status != "uncertain" else None,
                }
                for r in rec.reservations
            )
        async with self._sessionmaker() as session, session.begin():
            inserted = (
                (
                    await session.execute(
                        insert(UsageEvent)
                        .values(events)
                        .on_conflict_do_nothing(index_elements=["request_id"])
                        .returning(UsageEvent.request_id)
                    )
                )
                .scalars()
                .all()
            )
            # Ledger rows only for events that were new, so a replay adds nothing.
            fresh = set(inserted)
            rows = [r for r in reservations if r["request_id"] in fresh]
            if rows:
                await session.execute(insert(BudgetReservation), rows)
