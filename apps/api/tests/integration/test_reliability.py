"""Acceptance criterion 9 and other failure paths: nothing is ever recorded as free by
accident, and nothing is double counted."""

from __future__ import annotations

import asyncio

import pytest

from tests.integration.conftest import Api, World, chat
from tokenshield.worker import Worker

pytestmark = pytest.mark.integration


async def budget(api: Api, limit: str = "5") -> None:
    await api.ok(
        "POST",
        "/api/v1/budgets",
        {"name": "b", "scope_type": "global", "period": "monthly", "limit_usd": limit},
        status=201,
    )


async def test_ac9_timeout_is_uncertain_and_holds_reservation(api: Api, world: World) -> None:
    await budget(api)
    resp = await api.gateway(world.key, chat("slow [[slow:4]]"))  # provider timeout is 3s
    assert resp.status_code == 504 and resp.json()["error"]["code"] == "upstream_timeout"
    rid = resp.json()["error"]["details"]["request_id"]
    event = await api.ok("GET", f"/api/v1/usage/events/{rid}")
    assert event["status"] == "UNCERTAIN" and event["actual_cost_usd"] == 0
    (res,) = event["reservations"]
    assert res["status"] == "uncertain"
    (b,) = await api.ok("GET", "/api/v1/budgets")
    assert b["spent_usd"] == pytest.approx(event["estimated_cost_usd"]), "held, not released"

    settled = await Worker(api.app.state.container).reconcile_uncertain()
    assert settled == 1
    event = await api.ok("GET", f"/api/v1/usage/events/{rid}")
    assert event["reservations"][0]["status"] == "settled"
    assert event["reconciliations"][0]["delta_cost_usd"] == pytest.approx(
        event["estimated_cost_usd"]
    )
    assert await Worker(api.app.state.container).reconcile_uncertain() == 0, "idempotent"
    overview = await api.ok("GET", "/api/v1/analytics/overview?range=1h")
    assert overview["totals"]["cost_usd"] == pytest.approx(event["estimated_cost_usd"])


async def test_upstream_error_releases_reservation(api: Api, world: World) -> None:
    await budget(api)
    resp = await api.gateway(world.key, chat("boom [[error:500]]"))
    assert resp.status_code == 502
    (b,) = await api.ok("GET", "/api/v1/budgets")
    assert b["spent_usd"] == 0
    rid = resp.headers.get("x-request-id")
    events = (await api.ok("GET", "/api/v1/usage/events?status=ERROR"))["items"]
    assert len(events) == 1 and events[0]["reason"].startswith("Provider error") and rid


async def test_provider_status_is_passed_through_when_meaningful(api: Api, world: World) -> None:
    assert (await api.gateway(world.key, chat("x [[error:429]]"))).status_code == 429
    assert (await api.gateway(world.key, chat("y [[error:400]]"))).status_code == 400


async def test_unreachable_provider_is_not_sent_and_releases(api: Api, world: World) -> None:
    await budget(api)
    await api.ok(
        "PATCH", f"/api/v1/providers/{world.provider_id}", {"base_url": "http://127.0.0.1:1/v1"}
    )
    resp = await api.gateway(world.key, chat())
    assert resp.status_code == 502
    (b,) = await api.ok("GET", "/api/v1/budgets")
    assert b["spent_usd"] == 0


async def test_idempotency_key_never_double_bills(api: Api, world: World) -> None:
    await budget(api)
    headers = {"idempotency-key": "order-123", "x-tokenshield-cache": "off"}
    first = await api.gateway(world.key, chat("charge once"), headers)
    replay = await api.gateway(world.key, chat("charge once"), headers)
    assert first.status_code == replay.status_code == 200
    assert replay.headers["x-tokenshield-idempotent-replay"] == "true"
    assert replay.json() == first.json()
    assert (await api.mock_calls())["chat"] == 1
    events = (await api.ok("GET", "/api/v1/usage/events"))["items"]
    assert len(events) == 1


async def test_idempotency_in_flight_conflict(api: Api, world: World) -> None:
    headers = {"idempotency-key": "dup", "x-tokenshield-cache": "off"}
    a, b = await asyncio.gather(
        api.gateway(world.key, chat("slow one [[slow:0.6]]"), headers),
        api.gateway(world.key, chat("slow one [[slow:0.6]]"), headers),
    )
    assert sorted([a.status_code, b.status_code]) == [200, 409]


async def test_recording_is_idempotent_by_request_id(api: Api, world: World) -> None:
    from tokenshield.usage.recorder import UsageRecord, UsageRecorder

    recorder = UsageRecorder(api.app.state.container.db.sessionmaker)
    rec = UsageRecord(request_id="req_fixed", status="SUCCESS", http_status=200, actual_cost_nusd=5)
    await recorder.record(rec)
    await recorder.record(rec)
    page = await api.ok("GET", "/api/v1/usage/events?q=req_fixed")
    assert len(page["items"]) == 1


async def test_usage_ledger_is_append_only(api: Api, world: World) -> None:
    await api.gateway(world.key, chat())
    await api.drain()
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    async with api.app.state.container.db.sessionmaker() as session:
        for stmt in (
            "UPDATE usage_events SET actual_cost_nusd = 0",
            "DELETE FROM usage_events",
            "DELETE FROM audit_log",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(text(stmt))
            await session.rollback()


async def test_usage_stream_survives_a_crashed_worker(api: Api, world: World) -> None:
    """Entries read but never acked (worker died mid-batch) are reclaimed by another."""
    await api.gateway(world.key, chat())
    redis = api.app.state.container.redis
    from tokenshield.usage.recorder import GROUP, STREAM_KEY

    crashed = Worker(api.app.state.container)
    await crashed.ensure_group()
    await redis.xreadgroup(GROUP, "dead-worker", {STREAM_KEY: ">"}, count=10)  # read, never acked
    assert (await api.ok("GET", "/api/v1/usage/events"))["items"] == []
    survivor = Worker(api.app.state.container)
    assert await survivor.reclaim(min_idle_ms=0) == 1
    assert len((await api.ok("GET", "/api/v1/usage/events"))["items"]) == 1
    assert await redis.xlen(STREAM_KEY) == 0


async def test_redis_outage_records_directly_to_postgres(
    api: Api, world: World, settings: object
) -> None:
    from httpx import ASGITransport, AsyncClient

    from tokenshield.main import create_app

    app = create_app(settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"}))  # type: ignore[attr-defined]
    from asgi_lifespan import LifespanManager

    async with (
        LifespanManager(app, startup_timeout=60, shutdown_timeout=30),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json=chat("no redis here"),
            headers={"authorization": f"Bearer {world.key}"},
        )
        assert resp.status_code == 200
    events = (await api.ok("GET", "/api/v1/usage/events"))["items"]
    assert len(events) == 1 and events[0]["status"] == "SUCCESS"
