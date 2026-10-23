"""Acceptance criteria 2, 3 and 10: hard budgets hold, under concurrency, and fail closed."""

from __future__ import annotations

import asyncio

import pytest
from asgi_lifespan import LifespanManager

from tests.integration.conftest import Api, World, chat
from tokenshield.core.config import Settings
from tokenshield.main import create_app

pytestmark = pytest.mark.integration


async def budget(api: Api, **kw: object) -> dict[str, object]:
    body = {
        "name": "test budget",
        "scope_type": "global",
        "period": "monthly",
        "limit_usd": "1",
        "mode": "hard",
    } | kw
    result: dict[str, object] = await api.ok("POST", "/api/v1/budgets", body, status=201)
    return result


async def test_ac2_exhausted_budget_rejects_with_zero_upstream_calls(
    api: Api, world: World
) -> None:
    # chat-large: worst case for this prompt is about 1024 output tokens x $30/M = $0.03
    await budget(api, scope_type="project", scope_id=world.project_id, limit_usd="0.01")
    resp = await api.gateway(world.key, chat(model="chat-large"))
    assert resp.status_code == 402
    err = resp.json()["error"]
    assert err["code"] == "budget_exceeded"
    assert err["details"]["budget"] == "test budget"
    assert err["details"]["estimated_cost_usd"] > err["details"]["remaining_usd"]
    assert (await api.mock_calls()).get("chat", 0) == 0


async def test_ac3_concurrent_requests_cannot_overspend(api: Api, world: World) -> None:
    # Each request reserves exactly 1024 output tokens at $2/M plus a tiny input: the budget
    # fits 10 reservations and not 11.
    probe = await api.gateway(world.key, chat("probe"))
    est = float(probe.headers["x-tokenshield-estimated-cost-usd"])
    await api.client.post("/api/v1/cache/purge", json={})
    await budget(
        api,
        scope_type="api_key",
        scope_id=world.key_id,
        limit_usd=f"{est * 10.5 + float(probe.headers['x-tokenshield-cost-usd']):.9f}",
    )
    from httpx import AsyncClient

    async with AsyncClient() as c:
        await c.post(f"{api.mock_url}/stats/reset")
    results = await asyncio.gather(
        *(api.gateway(world.key, chat(f"probe {i} [[slow:1]]")) for i in range(50))
    )
    codes = [r.status_code for r in results]
    assert codes.count(200) == 10, codes
    assert codes.count(402) == 40
    assert (await api.mock_calls()).get("chat", 0) == 10
    budgets = await api.ok("GET", "/api/v1/budgets")
    assert budgets[0]["spent_usd"] <= budgets[0]["limit_usd"]


async def test_reservations_settle_to_actual_cost(api: Api, world: World) -> None:
    b = await budget(api, limit_usd="5")
    resp = await api.gateway(world.key, chat())
    actual = float(resp.headers["x-tokenshield-cost-usd"])
    estimated = float(resp.headers["x-tokenshield-estimated-cost-usd"])
    assert actual < estimated
    detail = await api.ok("GET", f"/api/v1/usage/events/{resp.headers['x-tokenshield-request-id']}")
    (res,) = detail["reservations"]
    assert res["status"] == "settled" and res["amount_usd"] == pytest.approx(estimated)
    assert res["actual_usd"] == pytest.approx(actual) and res["budget_name"] == b["name"]
    (status,) = await api.ok("GET", "/api/v1/budgets")
    assert status["spent_usd"] == pytest.approx(actual)


async def test_soft_budget_alerts_but_never_blocks(api: Api, world: World) -> None:
    await budget(api, mode="soft", limit_usd="0.000001", name="soft cap")
    resp = await api.gateway(world.key, chat())
    assert resp.status_code == 200
    for _ in range(50):
        alerts = await api.ok("GET", "/api/v1/alerts")
        if alerts["items"]:
            break
        await asyncio.sleep(0.05)
    assert any("soft cap" in a["message"] for a in alerts["items"])


async def test_unpriced_model_refused_under_hard_budget(api: Api, world: World) -> None:
    await api.ok(
        "POST",
        "/api/v1/models",
        {"alias": "mystery", "provider_id": world.provider_id, "upstream_model": "x"},
    )
    await budget(api, limit_usd="10")
    resp = await api.gateway(world.key, chat(model="mystery"))
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "model_unpriced"
    assert (await api.mock_calls()).get("chat", 0) == 0


async def test_per_user_budgets_are_independent(api: Api, world: World) -> None:
    probe = await api.gateway(world.key, chat("p"), {"x-tokenshield-cache": "off"})
    est = float(probe.headers["x-tokenshield-estimated-cost-usd"])
    actual = float(probe.headers["x-tokenshield-cost-usd"])
    # Room for one worst-case reservation, but not for a second on top of a settled request.
    limit = est + actual / 2
    await budget(api, scope_type="end_user", scope_id="*", period="daily", limit_usd=f"{limit:.9f}")
    a1 = await api.gateway(world.key, chat("q1"), {"x-tokenshield-user": "alice"})
    a2 = await api.gateway(world.key, chat("q2"), {"x-tokenshield-user": "alice"})
    b1 = await api.gateway(world.key, chat("q3"), {"x-tokenshield-user": "bob"})
    assert (a1.status_code, a2.status_code, b1.status_code) == (200, 402, 200)


async def test_counters_rebuild_from_postgres_after_redis_loss(api: Api, world: World) -> None:
    b = await budget(api, limit_usd="5")
    resp = await api.gateway(world.key, chat())
    spent = float(resp.headers["x-tokenshield-cost-usd"])
    await api.drain()  # the worker has persisted the event (it drains within milliseconds)
    from redis.asyncio import Redis

    redis = Redis.from_url(api.app.state.container.settings.redis_url)
    await redis.flushdb()
    await redis.aclose()
    (status,) = await api.ok("GET", "/api/v1/budgets")
    assert status["id"] == b["id"] and status["spent_usd"] == pytest.approx(spent)


async def test_ac10_redis_down_fails_closed_for_hard_budgets(
    api: Api, world: World, settings: Settings
) -> None:
    await budget(api, limit_usd="10")
    broken = settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"})
    app = create_app(broken)
    from httpx import ASGITransport, AsyncClient

    async with (
        LifespanManager(app, startup_timeout=60, shutdown_timeout=30),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        resp = await client.post(
            "/v1/chat/completions", json=chat(), headers={"authorization": f"Bearer {world.key}"}
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "budget_service_unavailable"
        ready = await client.get("/readyz")
        assert ready.status_code == 503
    assert (await api.mock_calls()).get("chat", 0) == 0


async def test_failure_mode_open_lets_traffic_through(
    api: Api, world: World, settings: Settings
) -> None:
    await budget(api, limit_usd="10")
    broken = settings.model_copy(
        update={"redis_url": "redis://127.0.0.1:1/0", "budget_failure_mode": "open"}
    )
    app = create_app(broken)
    from httpx import ASGITransport, AsyncClient

    async with (
        LifespanManager(app, startup_timeout=60, shutdown_timeout=30),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        resp = await client.post(
            "/v1/chat/completions", json=chat(), headers={"authorization": f"Bearer {world.key}"}
        )
        assert resp.status_code == 200
