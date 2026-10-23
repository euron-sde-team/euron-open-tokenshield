"""In-process TTL cache with cluster-wide invalidation through a Redis version stamp.

Gateway hot paths (API key lookup, catalog, budgets, rules) read configuration on every
request. Hitting Postgres for each would put the database on the critical path, so each
instance keeps a short-lived local copy. Any admin write bumps ``ts:cfg:version``; every
instance compares its stamp at most once per ``check_interval`` and drops its copy when the
stamp moved, so a revoked key stops working cluster wide within about a second.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

T = TypeVar("T")
VERSION_KEY = "ts:cfg:version"
log = logging.getLogger("tokenshield.cache")


class ConfigCache:
    def __init__(self, redis: Redis, *, ttl_s: float = 5.0, check_interval_s: float = 1.0) -> None:
        self._redis = redis
        self._ttl = ttl_s
        self._check_interval = check_interval_s
        self._entries: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._version: bytes | None = None
        self._checked_at = 0.0

    async def _sync_version(self) -> None:
        now = time.monotonic()
        if now - self._checked_at < self._check_interval:
            return
        self._checked_at = now
        try:
            version = cast(bytes | None, await self._redis.get(VERSION_KEY))
        except RedisError:
            # Without the stamp we cannot see invalidations: fall back to TTL expiry only.
            return
        if version != self._version:
            self._entries.clear()
            self._version = version

    async def get(self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        await self._sync_version()
        hit = self._entries.get(key)
        now = time.monotonic()
        if hit and hit[0] > now:
            return hit[1]  # type: ignore[no-any-return]
        # Single flight: one load per key per instance, concurrent callers share it.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = self._entries.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]  # type: ignore[no-any-return]
            value = await loader()
            self._entries[key] = (time.monotonic() + self._ttl, value)
            return value

    async def invalidate(self) -> None:
        """Called after every configuration write."""
        self._entries.clear()
        try:
            self._version = str(await self._redis.incr(VERSION_KEY)).encode()
            self._checked_at = time.monotonic()
        except RedisError:
            log.warning("could not bump config version; other instances refresh on TTL")
