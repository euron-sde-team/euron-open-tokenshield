import orjson

from tokenshield.gateway.service import GatewayService, idempotent_request_id, new_request_id


async def test_cached_completion_replays_as_openai_sse() -> None:
    body = {
        "id": "chatcmpl-1",
        "created": 1,
        "model": "chat-small",
        "choices": [
            {"message": {"role": "assistant", "content": "Hi there"}, "finish_reason": "stop"}
        ],
    }
    chunks = [c async for c in GatewayService._replay(body)]
    assert chunks[-1] == b"data: [DONE]\n\n"
    payloads = [orjson.loads(c[6:]) for c in chunks[:-1]]
    assert all(p["object"] == "chat.completion.chunk" for p in payloads)
    text = "".join(p["choices"][0]["delta"].get("content", "") for p in payloads)
    assert text == "Hi there"
    assert payloads[-1]["choices"][0]["finish_reason"] == "stop"


def test_request_ids() -> None:
    assert new_request_id() != new_request_id()
    assert idempotent_request_id("p", "k") == idempotent_request_id("p", "k")
    assert idempotent_request_id("p", "k") != idempotent_request_id("q", "k")
