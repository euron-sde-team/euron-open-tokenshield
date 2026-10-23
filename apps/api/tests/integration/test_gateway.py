"""Acceptance criteria 1 and 4: OpenAI compatibility and complete accounting."""

from __future__ import annotations

import httpx
import pytest
from openai import AsyncOpenAI

from tests.integration.conftest import Api, World, chat

pytestmark = pytest.mark.integration


def sdk(api: Api, key: str) -> AsyncOpenAI:
    http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://testserver"
    )
    return AsyncOpenAI(api_key=key, base_url="http://testserver/v1", http_client=http)


async def test_ac1_unmodified_openai_sdk_non_streaming(api: Api, world: World) -> None:
    client = sdk(api, world.key)
    resp = await client.chat.completions.create(
        model="chat-small",
        temperature=0,
        messages=[{"role": "user", "content": "What is photosynthesis?"}],
    )
    assert resp.model == "chat-small"
    assert "Photosynthesis" in (resp.choices[0].message.content or "")
    assert resp.usage is not None and resp.usage.prompt_tokens > 0


async def test_ac1_unmodified_openai_sdk_streaming(api: Api, world: World) -> None:
    client = sdk(api, world.key)
    stream = await client.chat.completions.create(
        model="chat-small",
        messages=[{"role": "user", "content": "Explain the water cycle"}],
        stream=True,
    )
    text = "".join([c.choices[0].delta.content or "" async for c in stream if c.choices])
    assert "water cycle" in text


async def test_ac1_sdk_lists_models_and_embeds(api: Api, world: World) -> None:
    client = sdk(api, world.key)
    models = await client.models.list()
    assert {m.id for m in models.data} >= {"chat-small", "chat-large", "claude", "embed-small"}
    emb = await client.embeddings.create(model="embed-small", input="hello world")
    assert len(emb.data[0].embedding) == 256


async def test_ac4_every_success_is_fully_accounted(api: Api, world: World) -> None:
    resp = await api.gateway(world.key, chat())
    assert resp.status_code == 200
    rid = resp.headers["x-tokenshield-request-id"]
    assert float(resp.headers["x-tokenshield-cost-usd"]) > 0
    event = await api.ok("GET", f"/api/v1/usage/events/{rid}")
    usage = resp.json()["usage"]
    assert event["status"] == "SUCCESS"
    assert event["input_tokens"] == usage["prompt_tokens"]
    assert event["output_tokens"] == usage["completion_tokens"]
    assert event["usage_source"] == "provider"
    assert event["model_alias"] == "chat-small" and event["provider"] == "Mock OpenAI"
    assert event["upstream_model"] == "mock-small"
    assert event["price_id"] is not None and event["price_version"] == 1 and event["priced"]
    expected = (usage["prompt_tokens"] * 1.0 + usage["completion_tokens"] * 2.0) / 1e6
    assert event["actual_cost_usd"] == pytest.approx(expected, rel=1e-6)
    assert event["latency_ms"] >= 0
    assert event["api_key_name"] == "prod" and event["project_name"] == "Alpha Tutor"


async def test_ac4_cached_input_tokens_are_priced_separately(api: Api, world: World) -> None:
    long_prompt = "context " * 1500  # the mock reports half of a long prompt as cached
    resp = await api.gateway(world.key, chat(long_prompt))
    usage = resp.json()["usage"]
    cached = usage["prompt_tokens_details"]["cached_tokens"]
    assert cached > 0
    event = await api.ok("GET", f"/api/v1/usage/events/{resp.headers['x-tokenshield-request-id']}")
    assert event["cached_input_tokens"] == cached
    expected = (
        (usage["prompt_tokens"] - cached) * 1.0 + cached * 0.5 + usage["completion_tokens"] * 2.0
    ) / 1e6
    assert event["actual_cost_usd"] == pytest.approx(expected, rel=1e-6)


async def test_ac4_unpriced_model_is_flagged_not_free(api: Api, world: World) -> None:
    await api.ok(
        "POST",
        "/api/v1/models",
        {"alias": "unpriced", "provider_id": world.provider_id, "upstream_model": "x"},
    )
    resp = await api.gateway(world.key, chat(model="unpriced"))
    assert resp.status_code == 200
    assert resp.headers["x-tokenshield-priced"] == "false"
    event = await api.ok("GET", f"/api/v1/usage/events/{resp.headers['x-tokenshield-request-id']}")
    assert event["priced"] is False and event["price_id"] is None


async def test_streaming_is_accounted_from_provider_usage(api: Api, world: World) -> None:
    async with api.client.stream(
        "POST",
        "/v1/chat/completions",
        json=chat(stream=True),
        headers={"authorization": f"Bearer {world.key}"},
    ) as resp:
        body = (await resp.aread()).decode()
        rid = resp.headers["x-tokenshield-request-id"]
    assert body.endswith("data: [DONE]\n\n")
    event = await api.ok("GET", f"/api/v1/usage/events/{rid}")
    assert event["stream"] and event["usage_source"] == "provider" and event["output_tokens"] > 0


async def test_anthropic_provider_through_openai_surface(api: Api, world: World) -> None:
    resp = await api.gateway(
        world.key,
        chat(
            model="claude",
            messages=[
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "How do I request a refund?"},
            ],
        ),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (
        data["object"] == "chat.completion" and "refund" in data["choices"][0]["message"]["content"]
    )
    assert (await api.mock_calls()).get("messages") == 1
    async with api.client.stream(
        "POST",
        "/v1/chat/completions",
        json=chat("Explain invoices", model="claude", stream=True),
        headers={"authorization": f"Bearer {world.key}"},
    ) as s:
        text = (await s.aread()).decode()
        rid = s.headers["x-tokenshield-request-id"]
    assert '"usage"' in text and text.endswith("data: [DONE]\n\n")
    event = await api.ok("GET", f"/api/v1/usage/events/{rid}")
    assert event["status"] == "SUCCESS" and event["output_tokens"] > 0


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({}, "invalid_api_key"),
        ({"authorization": "Bearer nonsense"}, "invalid_api_key"),
        ({"authorization": "Bearer tsk_abcdefabcdef_wrongsecret"}, "invalid_api_key"),
    ],
)
async def test_bad_keys_are_rejected(
    api: Api, world: World, headers: dict[str, str], code: str
) -> None:
    resp = await api.client.post(
        "/v1/chat/completions",
        json=chat(),
        headers={**headers, "authorization": headers.get("authorization", "")},
    )
    assert resp.status_code == 401 and resp.json()["error"]["code"] == code


async def test_revoked_key_stops_immediately(api: Api, world: World) -> None:
    assert (await api.gateway(world.key, chat())).status_code == 200
    await api.ok("POST", f"/api/v1/keys/{world.key_id}/revoke")
    resp = await api.gateway(world.key, chat())
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "api_key_revoked"


async def test_unknown_model_and_bad_bodies(api: Api, world: World) -> None:
    resp = await api.gateway(world.key, chat(model="nope"))
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "model_not_found"
    resp = await api.gateway(world.key, {"model": "chat-small", "messages": []})
    assert resp.status_code == 400
    resp = await api.client.post(
        "/v1/chat/completions",
        content=b"{not json",
        headers={"authorization": f"Bearer {world.key}"},
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_json"
    rejected = await api.ok("GET", "/api/v1/usage/events?status=REJECTED")
    assert {e["rule"] for e in rejected["items"]} >= {"model_not_found", "invalid_request"}
