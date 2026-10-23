"""Atomic budget reservations in Redis.

Checking recorded spend and then calling the provider is a race: two concurrent requests
both see room and both proceed. Instead every request reserves its worst-case cost against
all applicable budgets in **one Lua script**. Redis runs scripts atomically, so the check
and the increment cannot interleave across requests, instances or processes.

Each counter holds ``settled spend + outstanding reservations`` for one budget window.
When a counter is missing (first use in a window, or Redis lost its data) the script
reports it, the caller rebuilds the value from Postgres, and the reservation is retried.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError

from tokenshield.core.errors import DependencyUnavailableError

log = logging.getLogger("tokenshield.budgets")

# KEYS: counter keys. ARGV: amount, then per key (limit, hard 1|0, ttl seconds).
# Returns {1} on success, {0, index, current} when hard budget `index` (1-based) would be
# exceeded, {-1, index} when counter `index` must be hydrated first.
_RESERVE = """
local amount = tonumber(ARGV[1])
for i = 1, #KEYS do
  local cur = redis.call('GET', KEYS[i])
  if not cur then return {-1, i} end
  local base = 1 + (i - 1) * 3
  local limit = tonumber(ARGV[base + 1])
  local hard = ARGV[base + 2]
  if hard == '1' and tonumber(cur) + amount > limit then
    return {0, i, tonumber(cur)}
  end
end
for i = 1, #KEYS do
  redis.call('INCRBY', KEYS[i], amount)
  local ttl = tonumber(ARGV[1 + (i - 1) * 3 + 3])
  if ttl > 0 and redis.call('TTL', KEYS[i]) < 0 then redis.call('EXPIRE', KEYS[i], ttl) end
end
return {1}
"""

# Apply a signed delta to counters that still exist. A missing counter is rebuilt from
# Postgres on next use, which already reflects this settlement, so it is skipped.
_ADJUST = """
local delta = tonumber(ARGV[1])
for i = 1, #KEYS do
  if redis.call('EXISTS', KEYS[i]) == 1 then redis.call('INCRBY', KEYS[i], delta) end
end
return 1
"""

_HYDRATE = """
if redis.call('SET', KEYS[1], ARGV[1], 'NX') then
  if tonumber(ARGV[2]) > 0 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
end
return redis.call('GET', KEYS[1])
"""


@dataclass(frozen=True, slots=True)
class CounterSpec:
    budget_id: str
    key: str
    limit_nusd: int
    hard: bool
    ttl_s: int


@dataclass(frozen=True, slots=True)
class ReserveOutcome:
    ok: bool
    blocked: CounterSpec | None = None
    current_nusd: int = 0


Hydrator = Callable[[CounterSpec], Awaitable[int]]


class BudgetLedger:
    MAX_HYDRATE_ROUNDS = 8

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._reserve = redis.register_script(_RESERVE)
        self._adjust = redis.register_script(_ADJUST)
        self._hydrate = redis.register_script(_HYDRATE)

    async def reserve(
        self, counters: Sequence[CounterSpec], amount_nusd: int, hydrate: Hydrator
    ) -> ReserveOutcome:
        if not counters:
            return ReserveOutcome(ok=True)
        keys = [c.key for c in counters]
        args: list[int | str] = [amount_nusd]
        for c in counters:
            args += [c.limit_nusd, "1" if c.hard else "0", c.ttl_s]
        try:
            for _ in range(self.MAX_HYDRATE_ROUNDS):
                result = await self._reserve(keys=keys, args=args)
                code = int(result[0])
                if code == 1:
                    return ReserveOutcome(ok=True)
                spec = counters[int(result[1]) - 1]
                if code == 0:
                    return ReserveOutcome(ok=False, blocked=spec, current_nusd=int(result[2]))
                value = await hydrate(spec)
                await self._hydrate(keys=[spec.key], args=[value, spec.ttl_s])
        except RedisError as exc:
            raise DependencyUnavailableError(
                "Budget service unavailable; request refused to protect hard budgets",
                code="budget_service_unavailable",
            ) from exc
        raise DependencyUnavailableError(
            "Budget counters could not be initialised", code="budget_service_unavailable"
        )

    async def adjust(self, keys: Sequence[str], delta_nusd: int) -> None:
        """Move counters by ``delta`` (negative releases). Best effort, never raises."""
        if not keys or delta_nusd == 0:
            return
        try:
            await self._adjust(keys=list(keys), args=[delta_nusd])
        except RedisError:
            # Counter stays high: the safe direction. It self-corrects at window expiry
            # or when rebuilt from Postgres.
            log.warning("budget adjust failed", extra={"keys": len(keys), "delta": delta_nusd})

    @staticmethod
    def adjust_in(pipe: Pipeline, keys: Sequence[str], delta_nusd: int) -> None:
        """Queue an adjustment in a caller's pipeline. Plain EVAL on purpose: a registered
        script makes redis-py add a SCRIPT EXISTS round trip to every pipeline execute."""
        if keys and delta_nusd:
            pipe.eval(_ADJUST, len(keys), *keys, delta_nusd)

    async def current(self, keys: Sequence[str]) -> list[int | None]:
        if not keys:
            return []
        values = await self._redis.mget(list(keys))
        return [int(v) if v is not None else None for v in values]
