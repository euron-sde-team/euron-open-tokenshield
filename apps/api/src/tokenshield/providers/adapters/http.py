"""Shared HTTP plumbing: one pooled client, uniform error classification."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import orjson

from tokenshield.providers.adapters.base import (
    UpstreamHTTPError,
    UpstreamNotSentError,
    UpstreamUncertainError,
)

_NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
_UNCERTAIN = (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError, httpx.ReadError)


def build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
        http2=False,
        follow_redirects=False,
    )


def _error_message(resp: httpx.Response) -> tuple[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:500] or f"upstream returned {resp.status_code}", None
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err), data
    return str(err or data)[:500], data


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> dict[str, Any]:
    try:
        resp = await client.post(
            url,
            content=orjson.dumps(payload),
            headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=min(5.0, timeout_s)),
        )
    except _NOT_SENT as exc:
        raise UpstreamNotSentError(str(exc) or type(exc).__name__) from exc
    except _UNCERTAIN as exc:
        raise UpstreamUncertainError(str(exc) or type(exc).__name__) from exc
    if resp.status_code >= 400:
        message, body = _error_message(resp)
        raise UpstreamHTTPError(resp.status_code, message, body)
    data: dict[str, Any] = orjson.loads(resp.content)
    return data


@asynccontextmanager
async def stream_lines(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> AsyncIterator[AsyncIterator[str]]:
    try:
        async with client.stream(
            "POST",
            url,
            content=orjson.dumps(payload),
            headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=min(5.0, timeout_s)),
        ) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                message, body = _error_message(resp)
                raise UpstreamHTTPError(resp.status_code, message, body)
            yield _guard(resp.aiter_lines())
    except _NOT_SENT as exc:
        raise UpstreamNotSentError(str(exc) or type(exc).__name__) from exc
    except _UNCERTAIN as exc:
        raise UpstreamUncertainError(str(exc) or type(exc).__name__) from exc


async def _guard(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    try:
        async for line in lines:
            yield line
    except _UNCERTAIN as exc:
        raise UpstreamUncertainError(str(exc) or type(exc).__name__) from exc


def sse(obj: dict[str, Any]) -> bytes:
    return b"data: " + orjson.dumps(obj) + b"\n\n"


SSE_DONE = b"data: [DONE]\n\n"
