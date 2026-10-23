"""Adapters against an in-memory transport: no network, exact wire formats."""

import json
from collections.abc import Callable

import httpx
import pytest

from tokenshield.providers.adapters.anthropic import AnthropicAdapter
from tokenshield.providers.adapters.base import (
    StreamState,
    UpstreamHTTPError,
    UpstreamNotSentError,
    UpstreamTarget,
    UpstreamUncertainError,
)
from tokenshield.providers.adapters.openai import OpenAIAdapter

TARGET = UpstreamTarget("http://upstream.test/v1", "sk-test", "real-model", 5)


def client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_openai_chat_rewrites_model_and_sends_key() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={"id": "c1", "choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 3}},
        )

    result = await OpenAIAdapter(client(handler)).chat(
        TARGET, {"model": "alias", "messages": [], "stream_options": {}}
    )
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "real-model" and "stream_options" not in seen["body"]  # type: ignore[index,operator]
    assert result.usage.input_tokens == 9 and result.upstream_id == "c1"


async def test_openai_stream_captures_usage_and_text() -> None:
    sse = (
        'data: {"id":"s1","created":1,"model":"real","choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"id":"s1","model":"real","choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n'
        'data: {"id":"s1","model":"real","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(req: httpx.Request) -> httpx.Response:
        assert json.loads(req.content)["stream_options"] == {"include_usage": True}
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    state = StreamState()
    chunks = [
        c
        async for c in OpenAIAdapter(client(handler)).chat_stream(
            TARGET, {"model": "alias", "messages": []}, state
        )
    ]
    assert chunks[-1] == b"data: [DONE]\n\n"
    assert b'"model":"alias"' in chunks[0]
    assert "".join(state.text) == "Hello" and state.finish_reason == "stop"
    assert state.usage is not None and state.usage.output_tokens == 2


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.ConnectError("refused"), UpstreamNotSentError),
        (httpx.ReadTimeout("slow"), UpstreamUncertainError),
    ],
)
async def test_transport_errors_are_classified(exc: Exception, expected: type[Exception]) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise exc

    with pytest.raises(expected):
        await OpenAIAdapter(client(handler)).chat(TARGET, {"messages": []})


async def test_error_status_raises_with_provider_message() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    with pytest.raises(UpstreamHTTPError) as info:
        await OpenAIAdapter(client(handler)).chat(TARGET, {"messages": []})
    assert info.value.status == 429 and info.value.message == "slow down"


async def test_anthropic_chat_and_stream() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/messages"
        assert req.headers["x-api-key"] == "sk-test"
        body = json.loads(req.content)
        if body.get("stream"):
            events = [
                {
                    "type": "message_start",
                    "message": {
                        "id": "m1",
                        "usage": {"input_tokens": 11, "cache_read_input_tokens": 4},
                    },
                },
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Hi"},
                },
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {"type": "tool_use", "id": "t", "name": "f"},
                },
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "input_json_delta", "partial_json": "{}"},
                },
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 6},
                },
                {"type": "message_stop"},
            ]
            text = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
            return httpx.Response(200, text=text)
        return httpx.Response(
            200,
            json={
                "id": "m1",
                "content": [{"type": "text", "text": "Hi"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 11, "output_tokens": 6},
            },
        )

    target = UpstreamTarget("http://upstream.test", "sk-test", "claude", 5)
    adapter = AnthropicAdapter(client(handler))
    result = await adapter.chat(
        target, {"model": "alias", "messages": [{"role": "user", "content": "x"}]}
    )
    assert (
        result.body["choices"][0]["message"]["content"] == "Hi" and result.usage.output_tokens == 6
    )
    state = StreamState()
    chunks = [
        c async for c in adapter.chat_stream(target, {"model": "alias", "messages": []}, state)
    ]
    assert chunks[-1] == b"data: [DONE]\n\n"
    assert state.usage is not None and (
        state.usage.input_tokens,
        state.usage.cached_input_tokens,
        state.usage.output_tokens,
    ) == (15, 4, 6)
    assert state.tool_calls and "".join(state.text) == "Hi" and state.finish_reason == "stop"
    with pytest.raises(UpstreamHTTPError):
        await adapter.embeddings(target, {})
