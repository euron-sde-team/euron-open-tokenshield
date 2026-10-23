"""Redis client construction. One pooled client per application instance."""

from __future__ import annotations

from redis.asyncio import Redis


def create_redis(url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=False,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
        health_check_interval=15,
        retry_on_timeout=False,
    )
