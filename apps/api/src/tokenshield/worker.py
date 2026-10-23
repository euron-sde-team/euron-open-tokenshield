"""Background jobs. Run any number of worker processes: each job takes a Redis lease, so
exactly one instance runs it per interval.

Jobs:
  usage_drain    write buffered usage events to Postgres (every worker, consumer group)
  rollups        aggregate closed hours of usage into usage_rollups_hourly
  reconcile      settle UNCERTAIN requests at their reserved worst case
  cache_flush    move buffered cache entries and hit counters into Postgres
  policy_flush   move buffered policy trigger counts into Postgres
  cleanup        drop long-expired cache metadata and semantic vectors
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import monotonic as loop_time
from typing import cast

import orjson
from redis.exceptions import RedisError
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from tokenshield.budgets.models import BudgetReservation
from tokenshield.cache.models import CacheEntry, SemanticCacheEntry
from tokenshield.cache.store import NEW_ENTRIES_KEY, STATS_KEY
from tokenshield.core.config import Settings, get_settings
from tokenshield.core.container import Container
from tokenshield.core.logs import configure_logging
from tokenshield.core.tracing import configure_tracing
from tokenshield.gateway.service import POLICY_HITS_KEY
from tokenshield.policies.models import PolicyRule
from tokenshield.usage.models import ReconciliationEvent, UsageEvent
from tokenshield.usage.recorder import GROUP, STREAM_KEY, UsageRecorder, decode

log = logging.getLogger("tokenshield.worker")
Entry = tuple[bytes, dict[bytes, bytes]]

# One statement recomputes an hour from raw events plus reconciliation corrections, so
# re-running it is idempotent and late corrections land in the right hour.
ROLLUP_SQL = text(
    """
    INSERT INTO usage_rollups_hourly AS r (
      hour, project_id, api_key_id, model_alias, provider, status, cache_status, requests,
      input_tokens, cached_input_tokens, output_tokens, cost_nusd, avoided_cost_nusd,
      latency_ms_sum)
    SELECT date_trunc('hour', e.created_at),
           coalesce(e.project_id, '00000000-0000-0000-0000-000000000000'::uuid),
           coalesce(e.api_key_id, '00000000-0000-0000-0000-000000000000'::uuid),
           coalesce(e.model_alias, ''), coalesce(e.provider, ''), e.status, e.cache_status,
           count(*), sum(e.input_tokens), sum(e.cached_input_tokens), sum(e.output_tokens),
           sum(e.actual_cost_nusd + coalesce(rc.delta, 0)), sum(e.avoided_cost_nusd),
           sum(e.latency_ms)
      FROM usage_events e
      LEFT JOIN (SELECT request_id, sum(delta_cost_nusd) AS delta
                   FROM reconciliation_events GROUP BY request_id) rc
             ON rc.request_id = e.request_id
     WHERE e.created_at >= :start AND e.created_at < :end
     GROUP BY 1, 2, 3, 4, 5, 6, 7
    ON CONFLICT (hour, project_id, api_key_id, model_alias, provider, status, cache_status)
    DO UPDATE SET requests = excluded.requests, input_tokens = excluded.input_tokens,
      cached_input_tokens = excluded.cached_input_tokens, output_tokens = excluded.output_tokens,
      cost_nusd = excluded.cost_nusd, avoided_cost_nusd = excluded.avoided_cost_nusd,
      latency_ms_sum = excluded.latency_ms_sum
    """
)


class Worker:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.settings = container.settings
        self._stop = asyncio.Event()
        self.consumer = f"{socket.gethostname()}-{os.getpid()}"
        self.recorder = UsageRecorder(container.db.sessionmaker)

    def stop(self) -> None:
        self._stop.set()

    async def _lease(self, job: str, seconds: int) -> bool:
        try:
            return bool(await self.c.redis.set(f"ts:worker:lease:{job}", b"1", nx=True, ex=seconds))
        except RedisError:
            return False

    async def run_job(self, name: str, interval_s: int, fn: Callable[[], Awaitable[int]]) -> None:
        while not self._stop.is_set():
            if await self._lease(name, max(1, interval_s - 1)):
                try:
                    count = await fn()
                    if count:
                        log.info("job done", extra={"job": name, "count": count})
                except Exception:
                    log.exception("job failed", extra={"job": name})
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=interval_s)

    async def run(self) -> None:
        jobs = [
            ("rollups", 60, self.rollups),
            ("reconcile", 60, self.reconcile_uncertain),
            ("cache_flush", 10, self.flush_cache),
            ("policy_flush", 15, self.flush_policy_hits),
            ("cleanup", 3600, self.cleanup),
        ]
        log.info("worker started", extra={"jobs": ["usage_drain", *(j[0] for j in jobs)]})
        await asyncio.gather(self.usage_loop(), *(self.run_job(*j) for j in jobs))

    # ── Usage stream ────────────────────────────────────────────────────────

    async def ensure_group(self) -> None:
        try:
            await self.c.redis.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
        except RedisError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def drain_usage(self, *, block_ms: int = 0, count: int = 500) -> int:
        """Write one batch from the stream. Returns how many records were committed.

        Entries are acked only after the Postgres commit; a crash in between leaves them
        pending, and ``reclaim`` hands them to a live worker. Duplicate request ids are
        ignored by the insert, so at-least-once delivery never double counts.
        """
        await self.ensure_group()
        resp = await self.c.redis.xreadgroup(
            GROUP, self.consumer, {STREAM_KEY: ">"}, count=count, block=block_ms or None
        )
        stream_batches = cast(list[tuple[bytes, list[Entry]]], resp or [])
        return await self._commit([e for _, batch in stream_batches for e in batch])

    async def reclaim(self, min_idle_ms: int = 60_000) -> int:
        await self.ensure_group()
        result = await self.c.redis.xautoclaim(
            STREAM_KEY, GROUP, self.consumer, min_idle_time=min_idle_ms, start_id="0-0", count=500
        )
        claimed = cast(list[Entry], result[1]) if result else []
        return await self._commit(claimed)

    async def _commit(self, entries: list[Entry]) -> int:
        if not entries:
            return 0
        records = [decode(fields[b"r"]) for _, fields in entries if fields and b"r" in fields]
        await self.recorder.write(records)
        ids = [entry_id for entry_id, _ in entries]
        pipe = self.c.redis.pipeline(transaction=False)
        pipe.xack(STREAM_KEY, GROUP, *ids)
        pipe.xdel(STREAM_KEY, *ids)
        await pipe.execute()
        return len(records)

    async def usage_loop(self) -> None:
        last_reclaim = 0.0
        while not self._stop.is_set():
            try:
                if loop_time() - last_reclaim > 30:
                    await self.reclaim()
                    last_reclaim = loop_time()
                await self.drain_usage(block_ms=1000)
            except Exception:
                log.exception("usage drain failed; retrying")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=1)

    # ── Jobs ────────────────────────────────────────────────────────────────

    async def rollups(self) -> int:
        """Recompute the last few closed hours (late reconciliations land there too)."""
        now = datetime.now(UTC)
        open_hour = now.replace(minute=0, second=0, microsecond=0)
        async with self.c.db.sessionmaker() as session:
            first = await session.scalar(select(func.min(UsageEvent.created_at)))
            if first is None:
                return 0
            last_rolled = await session.scalar(text("SELECT max(hour) FROM usage_rollups_hourly"))
            start = (last_rolled - timedelta(hours=2)) if last_rolled else first
            start = start.replace(minute=0, second=0, microsecond=0)
            hours = 0
            hour = start
            while hour < open_hour:
                await session.execute(ROLLUP_SQL, {"start": hour, "end": hour + timedelta(hours=1)})
                hour += timedelta(hours=1)
                hours += 1
            await session.commit()
        return hours

    async def reconcile_uncertain(self) -> int:
        """Settle requests whose outcome was never known.

        The provider may have billed them, and the provider APIs used here do not expose a
        per-request usage lookup, so the conservative answer is the reserved worst case. A
        reconciliation event records it; the budget counters already hold that amount.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.uncertain_settle_after_s)
        async with self.c.db.sessionmaker() as session, session.begin():
            done = select(ReconciliationEvent.request_id)
            rows = (
                await session.execute(
                    select(UsageEvent.request_id, UsageEvent.estimated_cost_nusd)
                    .where(
                        UsageEvent.status == "UNCERTAIN",
                        UsageEvent.created_at < cutoff,
                        UsageEvent.request_id.not_in(done),
                    )
                    .limit(500)
                )
            ).all()
            if not rows:
                return 0
            now = datetime.now(UTC)
            await session.execute(
                insert(ReconciliationEvent),
                [
                    {
                        "request_id": rid,
                        "delta_cost_nusd": amount,
                        "reason": "uncertain_settled_at_reservation",
                        "details": {"settled_at": now.isoformat()},
                    }
                    for rid, amount in rows
                ],
            )
            await session.execute(
                update(BudgetReservation)
                .where(
                    BudgetReservation.request_id.in_([r[0] for r in rows]),
                    BudgetReservation.status == "uncertain",
                )
                .values(
                    status="settled",
                    actual_nusd=BudgetReservation.amount_nusd,
                    settled_at=now,
                )
            )
        return len(rows)

    async def flush_cache(self) -> int:
        redis = self.c.redis
        pipe = redis.pipeline(transaction=True)
        pipe.lrange(NEW_ENTRIES_KEY, 0, 999)
        pipe.ltrim(NEW_ENTRIES_KEY, 1000, -1)
        raw_entries, _ = await pipe.execute()
        # Swap the stats hash out atomically so no increment is lost between read and delete.
        stats: dict[bytes, bytes] = {}  # redis returns bytes: decode_responses=False
        tmp = f"{STATS_KEY}:flush"
        with contextlib.suppress(RedisError):
            if await redis.exists(STATS_KEY):
                await redis.rename(STATS_KEY, tmp)
                stats = cast(dict[bytes, bytes], await redis.hgetall(tmp))
                await redis.delete(tmp)
        if not raw_entries and not stats:
            return 0
        async with self.c.db.sessionmaker() as session, session.begin():
            if raw_entries:
                values = []
                for raw in raw_entries:
                    m = orjson.loads(raw)
                    values.append(
                        {
                            "key_hash": m["key"],
                            "project_id": m["project_id"],
                            "model_alias": m["model_alias"],
                            "kind": m.get("kind", "exact"),
                            "expires_at": datetime.fromisoformat(m["expires_at"]),
                            "prompt_excerpt": m.get("excerpt"),
                        }
                    )
                stmt = insert(CacheEntry).values(values)
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["key_hash"],
                        set_={"expires_at": stmt.excluded.expires_at, "invalidated": False},
                    )
                )
            per_key: dict[str, dict[str, int]] = {}
            for field, value in stats.items():
                key, metric = field.decode().rsplit("|", 1)
                per_key.setdefault(key, {})[metric] = int(value)
            now = datetime.now(UTC)
            for key, m in per_key.items():
                await session.execute(
                    update(CacheEntry)
                    .where(CacheEntry.key_hash == key)
                    .values(
                        hits=CacheEntry.hits + m.get("hits", 0),
                        tokens_saved=CacheEntry.tokens_saved + m.get("tokens", 0),
                        avoided_cost_nusd=CacheEntry.avoided_cost_nusd + m.get("avoided", 0),
                        last_hit_at=now,
                    )
                )
        return len(raw_entries) + len(stats)

    async def flush_policy_hits(self) -> int:
        redis = self.c.redis
        tmp = f"{POLICY_HITS_KEY}:flush"
        try:
            if not await redis.exists(POLICY_HITS_KEY):
                return 0
            await redis.rename(POLICY_HITS_KEY, tmp)
            hits = cast(dict[bytes, bytes], await redis.hgetall(tmp))
            await redis.delete(tmp)
        except RedisError:
            return 0
        async with self.c.db.sessionmaker() as session, session.begin():
            for rule_id, count in hits.items():
                await session.execute(
                    update(PolicyRule)
                    .where(PolicyRule.id == uuid.UUID(rule_id.decode()))
                    .values(triggered_count=PolicyRule.triggered_count + int(count))
                )
        return len(hits)

    async def cleanup(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=7)
        async with self.c.db.sessionmaker() as session, session.begin():
            a = await session.execute(delete(CacheEntry).where(CacheEntry.expires_at < cutoff))
            b = await session.execute(
                delete(SemanticCacheEntry).where(SemanticCacheEntry.expires_at < datetime.now(UTC))
            )
        return int(a.rowcount or 0) + int(b.rowcount or 0)  # type: ignore[attr-defined]


async def main(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    configure_tracing(settings, service="tokenshield-worker")
    container = Container.build(settings)
    worker = Worker(container)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.stop)
    try:
        await worker.run()
    finally:
        await container.close()
