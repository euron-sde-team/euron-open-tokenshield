"""Adapter for the Anthropic Messages API, translated to and from the OpenAI shape."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import orjson

from tokenshield.providers.adapters.base import (
    ChatResult,
    StreamState,
    UpstreamHTTPError,
    UpstreamTarget,
    Usage,
)
from tokenshield.providers.adapters.http import SSE_DONE, post_json, sse, stream_lines

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 1024

_STOP_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "pause_turn": "stop",
    "refusal": "content_filter",
}


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def _content_blocks(content: Any) -> list[dict[str, Any]] | str:
    if isinstance(content, str) or content is None:
        return content or ""
    blocks: list[dict[str, Any]] = []
    for part in content:
        kind = part.get("type")
        if kind == "text":
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif kind == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            if url.startswith("data:") and ";base64," in url:
                media, data = url[5:].split(";base64,", 1)
                blocks.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media, "data": data},
                    }
                )
            else:
                blocks.append({"type": "image", "source": {"type": "url", "url": url}})
    return blocks


def to_anthropic(body: dict[str, Any], upstream_model: str) -> dict[str, Any]:
    """Translate an OpenAI chat-completions request into a Messages API request."""
    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]] | str) -> None:
        # The Messages API requires alternating roles; merge consecutive same-role turns.
        if messages and messages[-1]["role"] == role:
            prev = messages[-1]["content"]
            prev_list = [{"type": "text", "text": prev}] if isinstance(prev, str) else prev
            new_list = [{"type": "text", "text": blocks}] if isinstance(blocks, str) else blocks
            messages[-1]["content"] = prev_list + new_list
        else:
            messages.append({"role": role, "content": blocks})

    for msg in body.get("messages") or []:
        role = msg.get("role")
        if role in ("system", "developer"):
            system_parts.append(_text_of(msg.get("content")))
        elif role == "user":
            push("user", _content_blocks(msg.get("content")))
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if text := _text_of(msg.get("content")):
                blocks.append({"type": "text", "text": text})
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                try:
                    args = orjson.loads(fn.get("arguments") or "{}")
                except orjson.JSONDecodeError:
                    args = {"_raw": fn.get("arguments")}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id"),
                        "name": fn.get("name"),
                        "input": args,
                    }
                )
            push("assistant", blocks or "")
        elif role == "tool":
            push(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": _text_of(msg.get("content")),
                    }
                ],
            )

    out: dict[str, Any] = {
        "model": upstream_model,
        "messages": messages,
        "max_tokens": body.get("max_completion_tokens")
        or body.get("max_tokens")
        or DEFAULT_MAX_TOKENS,
    }
    if system_parts:
        out["system"] = "\n\n".join(p for p in system_parts if p)
    for key in ("temperature", "top_p"):
        if body.get(key) is not None:
            out[key] = body[key]
    stop = body.get("stop")
    if stop:
        out["stop_sequences"] = [stop] if isinstance(stop, str) else list(stop)
    if tools := body.get("tools"):
        out["tools"] = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters") or {"type": "object"},
            }
            for t in tools
            if t.get("type") == "function"
        ]
        choice = body.get("tool_choice")
        if choice == "required":
            out["tool_choice"] = {"type": "any"}
        elif choice == "none":
            out["tool_choice"] = {"type": "none"}
        elif isinstance(choice, dict) and choice.get("function"):
            out["tool_choice"] = {"type": "tool", "name": choice["function"]["name"]}
    if user := body.get("user"):
        out["metadata"] = {"user_id": str(user)[:256]}
    return out


def usage_from(raw: dict[str, Any] | None) -> Usage:
    raw = raw or {}
    cached = int(raw.get("cache_read_input_tokens") or 0)
    created = int(raw.get("cache_creation_input_tokens") or 0)
    return Usage(
        input_tokens=int(raw.get("input_tokens") or 0) + cached + created,
        cached_input_tokens=cached,
        output_tokens=int(raw.get("output_tokens") or 0),
        source="provider",
    )


def to_openai(data: dict[str, Any], alias: str) -> dict[str, Any]:
    text = ""
    tool_calls: list[dict[str, Any]] = []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text += block.get("text", "")
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": orjson.dumps(block.get("input") or {}).decode(),
                    },
                }
            )
    usage = usage_from(data.get("usage"))
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": data.get("id") or "",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": alias,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": _STOP_REASONS.get(data.get("stop_reason") or "", "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": usage.input_tokens,
            "completion_tokens": usage.output_tokens,
            "total_tokens": usage.input_tokens + usage.output_tokens,
            "prompt_tokens_details": {"cached_tokens": usage.cached_input_tokens},
        },
    }


class AnthropicAdapter:
    kind = "anthropic"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @staticmethod
    def _headers(target: UpstreamTarget) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
        if target.api_key:
            headers["x-api-key"] = target.api_key
        return headers

    @staticmethod
    def _url(target: UpstreamTarget) -> str:
        base = target.base_url.rstrip("/")
        return base + ("/messages" if base.endswith("/v1") else "/v1/messages")

    async def chat(self, target: UpstreamTarget, body: dict[str, Any]) -> ChatResult:
        payload = to_anthropic(body, target.upstream_model)
        data = await post_json(
            self._client, self._url(target), payload, self._headers(target), target.timeout_s
        )
        return ChatResult(
            body=to_openai(data, body.get("model") or target.upstream_model),
            usage=usage_from(data.get("usage")),
            upstream_id=data.get("id"),
        )

    async def chat_stream(
        self, target: UpstreamTarget, body: dict[str, Any], state: StreamState
    ) -> AsyncIterator[bytes]:
        payload = {**to_anthropic(body, target.upstream_model), "stream": True}
        alias = body.get("model") or target.upstream_model
        usage = Usage(source="provider")
        tool_index: dict[int, int] = {}
        created = int(time.time())
        state.created = created

        def chunk(delta: dict[str, Any], finish: str | None = None) -> bytes:
            return sse(
                {
                    "id": state.response_id or "",
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": alias,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                }
            )

        async with stream_lines(
            self._client, self._url(target), payload, self._headers(target), target.timeout_s
        ) as lines:
            async for line in lines:
                if not line.startswith("data:"):
                    continue
                event = orjson.loads(line[5:].strip())
                kind = event.get("type")
                if kind == "message_start":
                    msg = event.get("message") or {}
                    state.response_id = msg.get("id")
                    start = usage_from(msg.get("usage"))
                    usage.input_tokens = start.input_tokens
                    usage.cached_input_tokens = start.cached_input_tokens
                    yield chunk({"role": "assistant", "content": ""})
                elif kind == "content_block_start":
                    block = event.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        state.tool_calls = True
                        idx = len(tool_index)
                        tool_index[event.get("index", 0)] = idx
                        yield chunk(
                            {
                                "tool_calls": [
                                    {
                                        "index": idx,
                                        "id": block.get("id"),
                                        "type": "function",
                                        "function": {"name": block.get("name"), "arguments": ""},
                                    }
                                ]
                            }
                        )
                elif kind == "content_block_delta":
                    delta = event.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        state.text.append(delta.get("text", ""))
                        yield chunk({"content": delta.get("text", "")})
                    elif delta.get("type") == "input_json_delta":
                        idx = tool_index.get(event.get("index", 0), 0)
                        yield chunk(
                            {
                                "tool_calls": [
                                    {
                                        "index": idx,
                                        "function": {"arguments": delta.get("partial_json", "")},
                                    }
                                ]
                            }
                        )
                elif kind == "message_delta":
                    out = (event.get("usage") or {}).get("output_tokens")
                    if out is not None:
                        usage.output_tokens = int(out)
                    reason = (event.get("delta") or {}).get("stop_reason")
                    if reason:
                        state.finish_reason = _STOP_REASONS.get(reason, "stop")
                elif kind == "error":
                    err = event.get("error") or {}
                    raise UpstreamHTTPError(502, str(err.get("message") or "stream error"), event)
        state.usage = usage
        yield chunk({}, state.finish_reason or "stop")
        yield sse(
            {
                "id": state.response_id or "",
                "object": "chat.completion.chunk",
                "created": created,
                "model": alias,
                "choices": [],
                "usage": {
                    "prompt_tokens": usage.input_tokens,
                    "completion_tokens": usage.output_tokens,
                    "total_tokens": usage.input_tokens + usage.output_tokens,
                    "prompt_tokens_details": {"cached_tokens": usage.cached_input_tokens},
                },
            }
        )
        yield SSE_DONE

    async def embeddings(
        self, target: UpstreamTarget, body: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        raise UpstreamHTTPError(400, "Anthropic does not offer an embeddings endpoint")
