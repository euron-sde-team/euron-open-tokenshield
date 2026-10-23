"""Gateway authentication and per-request context."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from redis.exceptions import RedisError
from sqlalchemy import update

from tokenshield.core.container import Container
from tokenshield.core.deps import get_container
from tokenshield.core.errors import AuthenticationError, PermissionDeniedError
from tokenshield.core.security import constant_time_equals, hash_key_secret, parse_api_key
from tokenshield.gateway.catalog import Catalog, KeyInfo, load_catalog, load_key
from tokenshield.gateway.context import RequestContext
from tokenshield.gateway.service import idempotent_request_id, new_request_id
from tokenshield.keys.models import ApiKey

_MAX_HEADER = 200


async def get_catalog(container: Annotated[Container, Depends(get_container)]) -> Catalog:
    async def load() -> Catalog:
        async with container.db.sessionmaker() as session:
            return await load_catalog(session, container.sealer)

    return await container.config_cache.get("catalog", load)


async def _touch_key(container: Container, key_id: uuid.UUID) -> None:
    """Record last use at most once a minute per key, off the request path."""
    try:
        if not await container.redis.set(f"ts:keyused:{key_id}", b"1", nx=True, ex=60):
            return
    except RedisError:
        return
    async with container.db.sessionmaker() as session, session.begin():
        await session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=datetime.now(UTC))
        )


_touch_tasks: set[asyncio.Task[None]] = set()


def _header(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    if value is None:
        return None
    value = value.strip()
    return value[:_MAX_HEADER] or None


async def authenticate_key(
    request: Request,
    container: Annotated[Container, Depends(get_container)],
    catalog: Annotated[Catalog, Depends(get_catalog)],
) -> RequestContext:
    raw = request.headers.get("authorization", "")
    token = (
        raw[7:].strip()
        if raw.lower().startswith("bearer ")
        else request.headers.get("x-api-key", "")
    )
    parsed = parse_api_key(token) if token else None
    if parsed is None:
        raise AuthenticationError(
            "Missing or malformed API key. Send 'Authorization: Bearer tsk_...'",
            code="invalid_api_key",
        )
    prefix, secret = parsed

    async def load() -> KeyInfo | None:
        async with container.db.sessionmaker() as session:
            return await load_key(session, prefix)

    key = await container.config_cache.get(f"key:{prefix}", load)
    expected = hash_key_secret(secret, container.settings.api_key_pepper)
    if key is None or not constant_time_equals(key.secret_hash, expected):
        raise AuthenticationError("Invalid API key", code="invalid_api_key")
    if key.revoked:
        raise AuthenticationError("This API key has been revoked", code="api_key_revoked")
    if key.expires_at and key.expires_at <= datetime.now(UTC):
        raise AuthenticationError("This API key has expired", code="api_key_expired")
    project = catalog.projects.get(key.project_id)
    if project is None:
        raise PermissionDeniedError(
            "The project for this key is archived or missing", code="project_unavailable"
        )

    task = asyncio.get_running_loop().create_task(_touch_key(container, key.id))
    _touch_tasks.add(task)
    task.add_done_callback(_touch_tasks.discard)

    idem = _header(request, "idempotency-key")
    request_id = idempotent_request_id(str(project.id), idem) if idem else new_request_id()
    with contextlib.suppress(Exception):
        request.state.request_id = request_id
    return RequestContext(
        request_id=request_id,
        project=project,
        key=key,
        end_user=_header(request, "x-tokenshield-user"),
        task_id=_header(request, "x-tokenshield-task-id"),
        cache_header=_header(request, "x-tokenshield-cache"),
        cache_scope=_header(request, "x-tokenshield-cache-scope"),
        idempotency_key=idem,
    )
