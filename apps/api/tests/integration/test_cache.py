"""Acceptance criteria 5, 6 and 7: caching avoids spend, never leaks across scopes, and
coalesces identical in-flight requests."""

from __future__ import annotations

import asyncio

import pytest

from tests.integration.conftest import Api, World, chat

pytestmark = pytest.mark.integration


async def test_ac5_identical_request_served_from_cache_without_upstream(
    api: Api, world: World
) -> None:
    first = await api.gateway(world.key, chat())
    assert first.headers["x-tokenshield-cache"] == "MISS"
    second = await api.gateway(world.key, chat())
    assert second.status_code == 200
    assert second.headers["x-tokenshield-cache"] == "HIT"
    assert second.json()["choices"] == first.json()["choices"]
    assert float(second.headers["x-tokenshield-avoided-cost-usd"]) == pytest.approx(
        float(first.headers["x-tokenshield-cost-usd"])
    )
    assert (await api.mock_calls())["chat"] == 1
    event = await api.ok(
        "GET", f"/api/v1/usage/events/{second.headers['x-tokenshield-request-id']}"
    )
    assert (
        event["cache_status"] == "HIT"
        and event["actual_cost_usd"] == 0
        and event["avoided_cost_usd"] > 0
    )


async def test_ac5_savings_appear_in_analytics_and_cache_stats(api: Api, world: World) -> None:
    for _ in range(3):
        await api.gateway(world.key, chat())
    overview = await api.ok("GET", "/api/v1/analytics/overview?range=1h")
    assert overview["totals"]["cache_hits"] == 2 and overview["totals"]["avoided_usd"] > 0
    await api.app.state.container.redis.ping()
    from tokenshield.worker import Worker

    await Worker(api.app.state.container).flush_cache()
    stats = await api.ok("GET", "/api/v1/cache/stats")
    assert (
        stats["entries_active"] == 1 and stats["hits_total"] == 2 and stats["avoided_cost_usd"] > 0
    )


async def test_cache_hit_replays_as_stream(api: Api, world: World) -> None:
    await api.gateway(world.key, chat())
    async with api.client.stream(
        "POST",
        "/v1/chat/completions",
        json=chat(stream=True),
        headers={"authorization": f"Bearer {world.key}"},
    ) as resp:
        text = (await resp.aread()).decode()
        assert resp.headers["x-tokenshield-cache"] == "HIT"
    assert "Photosynthesis" in text and text.endswith("data: [DONE]\n\n")
    assert (await api.mock_calls())["chat"] == 1


async def test_streamed_answers_populate_the_cache(api: Api, world: World) -> None:
    async with api.client.stream(
        "POST",
        "/v1/chat/completions",
        json=chat(stream=True),
        headers={"authorization": f"Bearer {world.key}"},
    ) as resp:
        await resp.aread()
    hit = await api.gateway(world.key, chat())
    assert hit.headers["x-tokenshield-cache"] == "HIT"


async def test_ac6_user_scoped_cache_never_crosses_users(api: Api, world: World) -> None:
    scoped = {"x-tokenshield-cache-scope": "user"}
    a = await api.gateway(
        world.key, chat("My progress summary"), scoped | {"x-tokenshield-user": "student-a"}
    )
    b = await api.gateway(
        world.key, chat("My progress summary"), scoped | {"x-tokenshield-user": "student-b"}
    )
    a2 = await api.gateway(
        world.key, chat("My progress summary"), scoped | {"x-tokenshield-user": "student-a"}
    )
    assert [r.headers["x-tokenshield-cache"] for r in (a, b, a2)] == ["MISS", "MISS", "HIT"]
    anonymous = await api.gateway(world.key, chat("My progress summary"), scoped)
    assert anonymous.headers["x-tokenshield-cache"] == "BYPASS", (
        "user scope without a user must not share"
    )


async def test_ac6_projects_never_share_entries(api: Api, world: World) -> None:
    other = await api.ok("POST", "/api/v1/projects", {"name": "Other"}, status=201)
    other_key = (
        await api.ok("POST", "/api/v1/keys", {"project_id": other["id"], "name": "k"}, status=201)
    )["key"]
    await api.gateway(world.key, chat())
    resp = await api.gateway(other_key, chat())
    assert resp.headers["x-tokenshield-cache"] == "MISS"


async def test_ac6_sensitive_and_sampled_requests_bypass_cache(api: Api, world: World) -> None:
    for _ in range(2):
        off = await api.gateway(world.key, chat("private"), {"x-tokenshield-cache": "off"})
        assert off.headers["x-tokenshield-cache"] == "BYPASS"
    sampled = chat("creative", temperature=0.9)
    for _ in range(2):
        assert (await api.gateway(world.key, sampled)).headers["x-tokenshield-cache"] == "BYPASS"
    assert (await api.mock_calls())["chat"] == 4


async def test_tool_call_answers_are_not_cached(api: Api, world: World) -> None:
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]
    for _ in range(2):
        r = await api.gateway(world.key, chat("check status [[tool]]", tools=tools))
        assert r.json()["choices"][0]["finish_reason"] == "tool_calls"
    assert (await api.mock_calls())["chat"] == 2


async def test_ac7_identical_concurrent_requests_coalesce(api: Api, world: World) -> None:
    body = chat("Summarise the term sheet [[slow:0.8]]")
    results = await asyncio.gather(*(api.gateway(world.key, body) for _ in range(6)))
    assert all(r.status_code == 200 for r in results)
    statuses = sorted(r.headers["x-tokenshield-cache"] for r in results)
    assert statuses.count("MISS") == 1 and statuses.count("COALESCED") == 5
    assert (await api.mock_calls())["chat"] == 1


async def test_failed_leader_releases_followers(api: Api, world: World) -> None:
    body = chat("fail me [[slow:0.5]] [[error:500]]")
    results = await asyncio.gather(*(api.gateway(world.key, body) for _ in range(3)))
    assert all(r.status_code == 502 for r in results)


async def test_invalidate_and_purge(api: Api, world: World) -> None:
    from tokenshield.worker import Worker

    await api.gateway(world.key, chat())
    await Worker(api.app.state.container).flush_cache()
    (entry,) = await api.ok("GET", "/api/v1/cache/entries")
    await api.ok("DELETE", f"/api/v1/cache/entries/{entry['key_hash']}")
    assert (await api.gateway(world.key, chat())).headers["x-tokenshield-cache"] == "MISS"
    await Worker(api.app.state.container).flush_cache()
    msg = await api.ok("POST", "/api/v1/cache/purge", {"project_id": world.project_id})
    assert "Invalidated 1" in msg["message"]
    assert (await api.gateway(world.key, chat())).headers["x-tokenshield-cache"] == "MISS"
