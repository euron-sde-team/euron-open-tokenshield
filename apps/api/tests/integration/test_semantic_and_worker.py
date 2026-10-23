"""Semantic cache (behind its flag), alert handling and the worker's job loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from tests.integration.conftest import Api, World, chat
from tokenshield.core.config import Settings
from tokenshield.main import create_app
from tokenshield.worker import Worker

pytestmark = pytest.mark.integration


async def indexed(api: Api, expected: int = 1) -> None:
    from sqlalchemy import func, select

    from tokenshield.cache.models import SemanticCacheEntry

    for _ in range(100):
        async with api.app.state.container.db.sessionmaker() as session:
            if (
                await session.scalar(select(func.count()).select_from(SemanticCacheEntry))
                >= expected
            ):
                return
        await asyncio.sleep(0.05)
    raise AssertionError("semantic vector was not indexed")


@pytest.fixture
async def semantic_client(
    api: Api, world: World, settings: Settings
) -> AsyncIterator[httpx.AsyncClient]:
    await api.ok("PATCH", f"/api/v1/projects/{world.project_id}", {"semantic_cache_enabled": True})
    app: FastAPI = create_app(
        settings.model_copy(update={"semantic_cache": True, "semantic_threshold": 0.9})
    )
    async with (
        LifespanManager(app, startup_timeout=60, shutdown_timeout=30),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c,
    ):
        c.headers["authorization"] = f"Bearer {world.key}"
        yield c


async def test_semantic_hit_for_reworded_question(
    api: Api, world: World, semantic_client: httpx.AsyncClient
) -> None:
    first = await semantic_client.post("/v1/chat/completions", json=chat("What is photosynthesis?"))
    assert first.headers["x-tokenshield-cache"] == "MISS"
    await asyncio.sleep(0.2)  # the vector is indexed in the background
    second = await semantic_client.post(
        "/v1/chat/completions", json=chat("Please explain photosynthesis")
    )
    assert second.headers["x-tokenshield-cache"] == "SEMANTIC_HIT"
    assert (
        second.json()["choices"][0]["message"]["content"]
        == first.json()["choices"][0]["message"]["content"]
    )
    unrelated = await semantic_client.post(
        "/v1/chat/completions", json=chat("How do I reset my password?")
    )
    assert unrelated.headers["x-tokenshield-cache"] == "MISS"
    assert (await api.mock_calls())["chat"] == 2


async def test_semantic_cache_respects_context(
    api: Api, world: World, semantic_client: httpx.AsyncClient
) -> None:
    await semantic_client.post("/v1/chat/completions", json=chat("What is photosynthesis?"))
    await indexed(api)
    other_context = {
        "model": "chat-small",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Answer as a pirate"},
            {"role": "user", "content": "Please explain photosynthesis"},
        ],
    }
    resp = await semantic_client.post("/v1/chat/completions", json=other_context)
    assert resp.headers["x-tokenshield-cache"] == "MISS"


async def test_alert_acknowledgement(api: Api, world: World) -> None:
    await api.ok(
        "POST",
        "/api/v1/budgets",
        {
            "name": "tiny",
            "scope_type": "global",
            "period": "daily",
            "limit_usd": "0.000001",
            "mode": "soft",
        },
        status=201,
    )
    await api.gateway(world.key, chat())
    for _ in range(40):
        alerts = await api.ok("GET", "/api/v1/alerts")
        if alerts["items"]:
            break
        await asyncio.sleep(0.05)
    assert alerts["unacknowledged"] >= 1
    await api.ok("POST", f"/api/v1/alerts/{alerts['items'][0]['id']}/ack")
    await api.ok("POST", "/api/v1/alerts/ack-all")
    assert (await api.ok("GET", "/api/v1/alerts"))["unacknowledged"] == 0
    assert len((await api.ok("GET", "/api/v1/alerts?include_acknowledged=true"))["items"]) >= 1
    assert (await api.client.post("/api/v1/alerts/99999/ack")).status_code == 404


async def test_worker_loop_runs_jobs_once_per_lease_and_stops(api: Api, world: World) -> None:
    await api.gateway(world.key, chat())
    worker = Worker(api.app.state.container)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.5)
    worker.stop()
    await asyncio.wait_for(task, timeout=5)
    from tokenshield.cache.store import NEW_ENTRIES_KEY

    assert await api.app.state.container.redis.llen(NEW_ENTRIES_KEY) == 0, "cache_flush ran"
    second = Worker(api.app.state.container)
    assert not await second._lease("rollups", 60), "lease held by the first worker"
    assert await second.cleanup() >= 0
