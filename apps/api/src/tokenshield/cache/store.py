"""Response cache and request coalescing on Redis.

Hot path cost: one GET on a hit, one SET plus one RPUSH on a store. Statistics are
buffered in Redis and flushed to Postgres by the worker, so caching never adds a database
round trip to a request.

Coalescing: the first request for a key takes a short ``SET NX`` lock and calls the
provider; identical requests arriving meanwhile wait for the cached result instead of
making their own upstream calls. If the leader fails, it drops the lock and a waiter takes
over, so a failure never strands followers.
"""

from __future__ import annotations

import asyncio
import time
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import orjson
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError

BODY_PREFIX = "ts:cache:body:"
LOCK_PREFIX = "ts:cache:lock:"
STATS_KEY = "ts:cache:stats"  # hash: <key>|hits, <key>|tokens, <key>|avoided
NEW_ENTRIES_KEY = "ts:cache:new"  # list of entry metadata for the worker
_COMPRESS_OVER = 1024

# One round trip on a miss: return the cached body, or try to become the leader.
# Returns {1, body} on a hit, {0, 1} when this caller now leads, {0, 0} when another leads.
_GET_OR_LEAD = """
local body = redis.call('GET', KEYS[1])
if body then return {1, body} end
if redis.call('SET', KEYS[2], '1', 'NX', 'PX', ARGV[1]) then return {0, 1} end
return {0, 0}
"""
_RAW, _ZLIB = b"r", b"z"


@dataclass(frozen=True, slots=True)
class CachedResponse:
    body: dict[str, Any]
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    created_at: float


def _encode(value: dict[str, Any]) -> bytes:
    raw = orjson.dumps(value)
    if len(raw) > _COMPRESS_OVER:
        return _ZLIB + zlib.compress(raw, 6)
    return _RAW + raw


def _decode(blob: bytes) -> dict[str, Any]:
    data = zlib.decompress(blob[1:]) if blob[:1] == _ZLIB else blob[1:]
    result: dict[str, Any] = orjson.loads(data)
    return result


class ResponseCache:
    def __init__(self, redis: Redis, *, coalesce_wait_s: float = 30.0) -> None:
        self._redis = redis
        self._coalesce_wait_s = coalesce_wait_s
        self._get_or_lead = redis.register_script(_GET_OR_LEAD)

    async def get_or_lead(self, key: str) -> tuple[CachedResponse | None, bool]:
        """(hit, leading). Without Redis: (None, True), i.e. a miss with nobody to wait for."""
        try:
            found, value = await self._get_or_lead(
                keys=[BODY_PREFIX + key, LOCK_PREFIX + key],
                args=[int(self._coalesce_wait_s * 1000)],
            )
        except RedisError:
            return None, True
        if int(found) == 1:
            return _to_cached(cast(bytes, value)), False
        return None, bool(int(value))

    async def get(self, key: str) -> CachedResponse | None:
        try:
            blob = await self._redis.get(BODY_PREFIX + key)
        except RedisError:
            return None  # a cache outage degrades to a miss, never to an error
        if blob is None:
            return None
        return _to_cached(cast(bytes, blob))

    async def put(
        self,
        key: str,
        body: dict[str, Any],
        *,
        ttl_s: int,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
        project_id: str,
        model_alias: str,
        kind: str = "exact",
        excerpt: str | None = None,
        pipe: Pipeline | None = None,
    ) -> None:
        now = time.time()
        record = {
            "body": body,
            "in": input_tokens,
            "cin": cached_input_tokens,
            "out": output_tokens,
            "at": now,
        }
        meta = {
            "key": key,
            "project_id": project_id,
            "model_alias": model_alias,
            "kind": kind,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl_s)).isoformat(),
            "excerpt": excerpt,
        }
        if pipe is not None:
            pipe.set(BODY_PREFIX + key, _encode(record), ex=ttl_s)
            pipe.rpush(NEW_ENTRIES_KEY, orjson.dumps(meta))
            return
        try:
            own = self._redis.pipeline(transaction=False)
            own.set(BODY_PREFIX + key, _encode(record), ex=ttl_s)
            own.rpush(NEW_ENTRIES_KEY, orjson.dumps(meta))
            await own.execute()
        except RedisError:
            return

    @staticmethod
    def record_hit(pipe: Pipeline, key: str, tokens: int, avoided_nusd: int) -> None:
        pipe.hincrby(STATS_KEY, f"{key}|hits", 1)
        pipe.hincrby(STATS_KEY, f"{key}|tokens", tokens)
        pipe.hincrby(STATS_KEY, f"{key}|avoided", avoided_nusd)

    async def invalidate(self, keys: list[str]) -> int:
        if not keys:
            return 0
        removed = await self._redis.delete(*[BODY_PREFIX + k for k in keys])
        return int(removed)

    async def try_lead(self, key: str) -> bool:
        """Become the single request allowed to call the provider for ``key``."""
        try:
            return bool(
                await self._redis.set(
                    LOCK_PREFIX + key, b"1", nx=True, px=int(self._coalesce_wait_s * 1000)
                )
            )
        except RedisError:
            return True  # without Redis there is nobody to coordinate with: just proceed

    @staticmethod
    def release_lead_in(pipe: Pipeline, key: str) -> None:
        pipe.delete(LOCK_PREFIX + key)

    async def release_lead(self, key: str) -> None:
        try:
            await self._redis.delete(LOCK_PREFIX + key)
        except RedisError:
            return

    async def wait_for(self, key: str) -> CachedResponse | None:
        """Wait for the leader's result. None means the leader gave up: proceed alone."""
        deadline = time.monotonic() + self._coalesce_wait_s
        delay = 0.02
        while time.monotonic() < deadline:
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 0.25)
            hit = await self.get(key)
            if hit is not None:
                return hit
            try:
                if not await self._redis.exists(LOCK_PREFIX + key):
                    return await self.get(key)
            except RedisError:
                return None
        return None


def _to_cached(blob: bytes) -> CachedResponse:
    data = _decode(blob)
    return CachedResponse(
        body=data["body"],
        input_tokens=int(data["in"]),
        cached_input_tokens=int(data.get("cin", 0)),
        output_tokens=int(data["out"]),
        created_at=float(data["at"]),
    )
