"""Mock LLM provider speaking the OpenAI and Anthropic APIs.

Deterministic: the same prompt always yields the same answer and the same token counts,
so tests can assert exact accounting. Control markers in the last user message:

  [[slow:SECONDS]]   wait before answering (timeouts, coalescing, concurrency)
  [[error:STATUS]]   answer with that HTTP error status
  [[tool]]           answer with a tool call instead of text
  [[long]]           a long answer (truncated by max_tokens -> finish_reason "length")
  [[drop]]           close the connection without answering

``GET /stats`` returns call counts per endpoint, ``POST /stats/reset`` clears them. Tests
use it to prove that a blocked or cached request never reached the provider.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import time
from collections import Counter
from collections.abc import AsyncIterator
from typing import Any

import orjson
import tiktoken
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

app = FastAPI(title="TokenShield mock LLM", docs_url=None, redoc_url=None)
calls: Counter[str] = Counter()
_enc = tiktoken.get_encoding("o200k_base")

KNOWLEDGE = {
    "photosynthesis": "Photosynthesis is how plants, algae and some bacteria turn light into "
    "chemical energy. Chlorophyll captures sunlight, water is split to release oxygen, and the "
    "energy is used to fix carbon dioxide into glucose in the Calvin cycle.",
    "refund": "You can request a refund within 30 days of purchase from Settings, then Billing. "
    "Refunds return to the original payment method within five to seven business days.",
    "password": "To reset your password, choose 'Forgot password' on the sign-in page and follow "
    "the link we email you. The link is valid for one hour.",
    "invoice": "Invoices are generated on the first of each month and can be downloaded as PDF "
    "from the Billing page. Each line shows the plan, seats and any usage charges.",
    "python": "Here is a compact approach: read the file line by line, split each record, and "
    "accumulate totals in a dictionary keyed by category. Sorting the items by value gives the "
    "ranking you want.",
}
LONG_TEXT = " ".join(
    f"Section {i}: the system processes the request, validates its inputs, applies the "
    "configured rules and records an audit entry before returning a result."
    for i in range(1, 400)
)


def _last_user(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def _prompt_tokens(messages: list[dict[str, Any]], system: str | None = None) -> int:
    text = (system or "") + "".join(
        str(
            m.get("content")
            if isinstance(m.get("content"), str)
            else orjson.dumps(m.get("content"))
        )
        for m in messages
    )
    return len(_enc.encode(text, disallowed_special=())) + 3 * len(messages) + 3


def _answer(prompt: str) -> str:
    if "[[long]]" in prompt:
        return LONG_TEXT
    lower = prompt.lower()
    for topic, text in KNOWLEDGE.items():
        if topic in lower:
            return text
    clean = re.sub(r"\[\[.*?\]\]", "", prompt).strip()
    digest = hashlib.sha256(clean.encode()).hexdigest()[:6]
    subject = clean[:80] or "your request"
    return (
        f'Here is a concise answer about "{subject}". The key points are the goal, the '
        f"constraints and the next step. Reference {digest}."
    )


def _truncate(text: str, max_tokens: int | None) -> tuple[str, int, str]:
    tokens = _enc.encode(text)
    if max_tokens and len(tokens) > max_tokens:
        return _enc.decode(tokens[:max_tokens]), max_tokens, "length"
    return text, len(tokens), "stop"


async def _controls(prompt: str) -> Response | None:
    if m := re.search(r"\[\[slow:(\d+(?:\.\d+)?)\]\]", prompt):
        await asyncio.sleep(float(m.group(1)))
    if m := re.search(r"\[\[error:(\d{3})\]\]", prompt):
        status = int(m.group(1))
        return JSONResponse(
            {"error": {"message": f"mock error {status}", "type": "mock_error"}}, status_code=status
        )
    if "[[drop]]" in prompt:
        raise ConnectionAbortedError("mock drop")
    return None


def _latency(prompt: str) -> float:
    if "[[fast]]" in prompt or "[[slow" in prompt:
        return 0.0
    h = int(hashlib.sha256(prompt.encode()).hexdigest()[:4], 16)
    return 0.15 + (h % 450) / 1000


def _cached(prompt_tokens: int) -> int:
    # Mimic provider prompt caching: long prompts report half their tokens as cached.
    return (prompt_tokens // 2 // 128) * 128 if prompt_tokens >= 1024 else 0


@app.get("/stats")
async def stats() -> dict[str, int]:
    return dict(calls)


@app.post("/stats/reset")
async def reset() -> dict[str, bool]:
    calls.clear()
    return {"ok": True}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    calls["models"] += 1
    names = ["mock-gpt-small", "mock-gpt-large", "mock-claude", "mock-embed"]
    return {"object": "list", "data": [{"id": n, "object": "model"} for n in names]}


@app.post("/v1/chat/completions")
async def chat(request: Request) -> Response:
    calls["chat"] += 1
    body = await request.json()
    messages = body.get("messages") or []
    prompt = _last_user(messages)
    if (ctl := await _controls(prompt)) is not None:
        return ctl
    await asyncio.sleep(_latency(prompt))
    p_tokens = _prompt_tokens(messages)
    max_tokens = body.get("max_completion_tokens") or body.get("max_tokens")
    rid = "chatcmpl-mock" + hashlib.sha256(orjson.dumps(messages)).hexdigest()[:12]
    created = int(time.time())
    model = body.get("model", "mock")
    usage_base = {
        "prompt_tokens": p_tokens,
        "prompt_tokens_details": {"cached_tokens": _cached(p_tokens)},
    }

    if "[[tool]]" in prompt and body.get("tools"):
        fn = body["tools"][0]["function"]["name"]
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_mock1",
                    "type": "function",
                    "function": {"name": fn, "arguments": '{"query": "status"}'},
                }
            ],
        }
        usage = usage_base | {"completion_tokens": 12, "total_tokens": p_tokens + 12}
        return JSONResponse(
            {
                "id": rid,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}],
                "usage": usage,
            }
        )

    text, out_tokens, finish = _truncate(_answer(prompt), max_tokens)
    usage = usage_base | {"completion_tokens": out_tokens, "total_tokens": p_tokens + out_tokens}
    if body.get("stream"):
        include_usage = (body.get("stream_options") or {}).get("include_usage")

        async def gen() -> AsyncIterator[bytes]:
            base = {
                "id": rid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
            }
            yield (
                b"data: "
                + orjson.dumps(
                    base
                    | {
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": ""},
                                "finish_reason": None,
                            }
                        ]
                    }
                )
                + b"\n\n"
            )
            words = re.findall(r"\S+\s*", text)
            for i in range(0, len(words), 4):
                await asyncio.sleep(0.01)
                piece = "".join(words[i : i + 4])
                yield (
                    b"data: "
                    + orjson.dumps(
                        base
                        | {
                            "choices": [
                                {"index": 0, "delta": {"content": piece}, "finish_reason": None}
                            ]
                        }
                    )
                    + b"\n\n"
                )
            yield (
                b"data: "
                + orjson.dumps(
                    base | {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
                )
                + b"\n\n"
            )
            if include_usage:
                yield b"data: " + orjson.dumps(base | {"choices": [], "usage": usage}) + b"\n\n"
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")
    return JSONResponse(
        {
            "id": rid,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": finish,
                }
            ],
            "usage": usage,
        }
    )


def _embed(text: str, dims: int = 256) -> list[float]:
    """Hashed bag of words: texts sharing words get similar vectors."""
    vec = [0.0] * dims
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {
        "the",
        "a",
        "an",
        "is",
        "what",
        "how",
        "do",
        "i",
        "to",
        "of",
        "and",
        "my",
        "can",
        "you",
        "please",
        "me",
        "tell",
        "explain",
    }
    for w in words:
        if w in stop:
            continue
        h = int(hashlib.md5(w.encode(), usedforsecurity=False).hexdigest(), 16)
        vec[h % dims] += 1.0 if (h >> 8) % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> Response:
    calls["embeddings"] += 1
    body = await request.json()
    inputs = body.get("input")
    items = [inputs] if isinstance(inputs, str) else list(inputs or [])
    tokens = sum(len(_enc.encode(str(i))) for i in items)
    return JSONResponse(
        {
            "object": "list",
            "model": body.get("model"),
            "data": [
                {"object": "embedding", "index": i, "embedding": _embed(str(t))}
                for i, t in enumerate(items)
            ],
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
        }
    )


@app.post("/v1/messages")
async def anthropic_messages(request: Request) -> Response:
    calls["messages"] += 1
    body = await request.json()
    messages = body.get("messages") or []
    prompt = _last_user(messages)
    if (ctl := await _controls(prompt)) is not None:
        return ctl
    await asyncio.sleep(_latency(prompt))
    p_tokens = _prompt_tokens(messages, body.get("system"))
    cached = _cached(p_tokens)
    text, out_tokens, finish = _truncate(_answer(prompt), body.get("max_tokens"))
    stop = "max_tokens" if finish == "length" else "end_turn"
    mid = "msg_mock" + hashlib.sha256(orjson.dumps(messages)).hexdigest()[:12]
    usage = {
        "input_tokens": p_tokens - cached,
        "cache_read_input_tokens": cached,
        "output_tokens": out_tokens,
    }
    if body.get("stream"):

        async def gen() -> AsyncIterator[bytes]:
            def ev(name: str, data: dict[str, Any]) -> bytes:
                return f"event: {name}\n".encode() + b"data: " + orjson.dumps(data) + b"\n\n"

            yield ev(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": mid,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "usage": {**usage, "output_tokens": 1},
                    },
                },
            )
            yield ev(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            words = re.findall(r"\S+\s*", text)
            for i in range(0, len(words), 4):
                await asyncio.sleep(0.01)
                yield ev(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "".join(words[i : i + 4])},
                    },
                )
            yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
            yield ev(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": stop},
                    "usage": {"output_tokens": out_tokens},
                },
            )
            yield ev("message_stop", {"type": "message_stop"})

        return StreamingResponse(gen(), media_type="text/event-stream")
    return JSONResponse(
        {
            "id": mid,
            "type": "message",
            "role": "assistant",
            "model": body.get("model"),
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop,
            "usage": usage,
        }
    )
