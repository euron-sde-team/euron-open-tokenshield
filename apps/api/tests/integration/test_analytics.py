"""Acceptance criterion 11: usage, rejections, cache hits and savings are inspectable and
exportable; rollups agree with raw events."""

from __future__ import annotations

import csv
import io

import pytest

from tests.integration.conftest import Api, World, chat
from tokenshield.worker import Worker

pytestmark = pytest.mark.integration


async def traffic(api: Api, world: World) -> None:
    await api.ok(
        "POST",
        "/api/v1/policies",
        {"name": "big", "kind": "max_input_tokens", "params": {"limit": 40}},
        status=201,
    )
    for _ in range(3):
        await api.gateway(world.key, chat())  # 1 miss + 2 hits
    await api.gateway(world.key, chat("Explain invoices", model="claude"))
    await api.gateway(world.key, chat("too long " * 60))  # rejected
    await api.drain()


async def test_overview_breakdown_timeseries(api: Api, world: World) -> None:
    await traffic(api, world)
    ov = (await api.ok("GET", "/api/v1/analytics/overview?range=24h"))["totals"]
    assert (ov["requests"], ov["succeeded"], ov["rejected"], ov["cache_hits"]) == (5, 4, 1, 2)
    assert ov["cost_usd"] > 0 and ov["avoided_usd"] > 0 and ov["cache_hit_rate"] == 0.5
    by_model = await api.ok("GET", "/api/v1/analytics/breakdown?by=model&range=24h")
    assert {r["label"] for r in by_model} >= {"chat-small", "claude"}
    by_project = await api.ok("GET", "/api/v1/analytics/breakdown?by=project&range=24h")
    assert by_project[0]["label"] == "Alpha Tutor"
    by_key = await api.ok("GET", "/api/v1/analytics/breakdown?by=api_key&range=24h")
    assert by_key[0]["label"] == "prod"
    series = await api.ok("GET", "/api/v1/analytics/timeseries?range=24h")
    assert len(series) >= 24 and sum(p["requests"] for p in series) == 5
    week = await api.ok("GET", "/api/v1/analytics/timeseries?range=7d")
    assert 7 <= len(week) <= 8


async def test_rollups_match_raw_events(api: Api, world: World) -> None:
    await traffic(api, world)
    container = api.app.state.container
    async with container.db.sessionmaker() as session:
        from sqlalchemy import text

        # Age every event by two hours so they fall into closed, rollable hours.
        await session.execute(
            text("ALTER TABLE usage_events DISABLE TRIGGER usage_events_append_only")
        )
        await session.execute(
            text("UPDATE usage_events SET created_at = created_at - interval '2 hours'")
        )
        await session.execute(
            text("ALTER TABLE usage_events ENABLE TRIGGER usage_events_append_only")
        )
        await session.commit()
    await container.redis.flushdb()
    raw = (await api.ok("GET", "/api/v1/analytics/overview?range=24h"))["totals"]
    assert await Worker(container).rollups() >= 1
    await container.redis.flushdb()
    rolled = (await api.ok("GET", "/api/v1/analytics/overview?range=24h"))["totals"]
    assert rolled == raw


async def test_request_log_filters_and_pagination(api: Api, world: World) -> None:
    await traffic(api, world)
    rejected = await api.ok("GET", "/api/v1/usage/events?status=REJECTED")
    assert len(rejected["items"]) == 1 and rejected["items"][0]["rule"] == "prompt_too_large"
    hits = await api.ok("GET", "/api/v1/usage/events?cache_status=HIT")
    assert len(hits["items"]) == 2
    page1 = await api.ok("GET", "/api/v1/usage/events?limit=2")
    page2 = await api.ok("GET", f"/api/v1/usage/events?limit=2&cursor={page1['next_cursor']}")
    page3 = await api.ok("GET", f"/api/v1/usage/events?limit=2&cursor={page2['next_cursor']}")
    ids = [e["id"] for p in (page1, page2, page3) for e in p["items"]]
    assert len(ids) == 5 == len(set(ids)) and page3["next_cursor"] is None
    assert (await api.client.get("/api/v1/usage/events/req_missing")).status_code == 404


async def test_ac11_export_csv(api: Api, world: World) -> None:
    await traffic(api, world)
    export = await api.ok("POST", "/api/v1/exports", {"range": "24h"}, status=201)
    assert export["rows"] == 5 and export["bytes"] > 0
    link = await api.ok("GET", f"/api/v1/exports/{export['id']}/download")
    assert link["filename"].endswith(".csv")
    resp = await api.fetch(link["url"])
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 5 and {r["status"] for r in rows} == {"SUCCESS", "REJECTED"}
    assert sum(r["cache_status"] == "HIT" for r in rows) == 2
    listed = await api.ok("GET", "/api/v1/exports")
    assert listed[0]["id"] == export["id"]


async def test_export_neutralises_formula_injection(api: Api, world: World) -> None:
    await api.gateway(world.key, chat(), {"x-tokenshield-user": "=HYPERLINK(evil)"})
    export = await api.ok("POST", "/api/v1/exports", {"range": "24h"}, status=201)
    resp = await api.fetch((await api.ok("GET", f"/api/v1/exports/{export['id']}/download"))["url"])
    assert "'=HYPERLINK(evil)" in resp.text


async def test_analytics_is_cached_briefly(api: Api, world: World) -> None:
    await api.ok("GET", "/api/v1/analytics/overview?range=1h")
    await api.gateway(world.key, chat())
    cached = (await api.ok("GET", "/api/v1/analytics/overview?range=1h"))["totals"]["requests"]
    assert cached == 0, "served from the 10s analytics cache"
    await api.app.state.container.redis.flushdb()
    assert (await api.ok("GET", "/api/v1/analytics/overview?range=1h"))["totals"]["requests"] == 1
