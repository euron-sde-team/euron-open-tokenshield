"""Adapter for any OpenAI-compatible API: OpenAI, Azure-style proxies, Ollama, vLLM,
LM Studio, Groq, Together and others that implement ``/chat/completions``."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import orjson

from tokenshield.providers.adapters.base import (
    ChatResult,
    StreamState,
    UpstreamTarget,
    Usage,
)
from tokenshield.providers.adapters.http import SSE_DONE, post_json, sse, stream_lines


def parse_usage(raw: dict[str, Any] | None) -> Usage | None:
    if not raw:
        return None
    details = raw.get("prompt_tokens_details") or {}
    return Usage(
        input_tokens=int(raw.get("prompt_tokens") or 0),
        cached_input_tokens=int(details.get("cached_tokens") or 0),
        output_tokens=int(raw.get("completion_tokens") or 0),
        source="provider",
    )


class OpenAIAdapter:
    kind = "openai"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @staticmethod
    def _headers(target: UpstreamTarget) -> dict[str, str]:
        headers = {"content-type": "application/json", "accept": "application/json"}
        if target.api_key:
            headers["authorization"] = f"Bearer {target.api_key}"
        return headers

    @staticmethod
    def _url(target: UpstreamTarget, path: str) -> str:
        return target.base_url.rstrip("/") + path

    async def chat(self, target: UpstreamTarget, body: dict[str, Any]) -> ChatResult:
        payload = {**body, "model": target.upstream_model, "stream": False}
        payload.pop("stream_options", None)
        data = await post_json(
            self._client,
            self._url(target, "/chat/completions"),
            payload,
            self._headers(target),
            target.timeout_s,
        )
        usage = parse_usage(data.get("usage")) or Usage(source="estimate")
        return ChatResult(body=data, usage=usage, upstream_id=data.get("id"))

    async def chat_stream(
        self, target: UpstreamTarget, body: dict[str, Any], state: StreamState
    ) -> AsyncIterator[bytes]:
        # Ask for the final usage chunk so streamed calls are billed from provider counts.
        payload = {
            **body,
            "model": target.upstream_model,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        async with stream_lines(
            self._client,
            self._url(target, "/chat/completions"),
            payload,
            self._headers(target),
            target.timeout_s,
        ) as lines:
            async for line in lines:
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = orjson.loads(data)
                state.response_id = state.response_id or chunk.get("id")
                state.created = state.created or chunk.get("created") or int(time.time())
                if usage := parse_usage(chunk.get("usage")):
                    state.usage = usage
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if content := delta.get("content"):
                        state.text.append(content)
                    if delta.get("tool_calls"):
                        state.tool_calls = True
                    if choice.get("finish_reason"):
                        state.finish_reason = choice["finish_reason"]
                # Upstream echoes its own model id; clients asked for the gateway alias.
                if "model" in chunk and body.get("model"):
                    chunk["model"] = body["model"]
                yield sse(chunk)
        yield SSE_DONE

    async def embeddings(
        self, target: UpstreamTarget, body: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        payload = {**body, "model": target.upstream_model}
        data = await post_json(
            self._client,
            self._url(target, "/embeddings"),
            payload,
            self._headers(target),
            target.timeout_s,
        )
        raw = data.get("usage") or {}
        usage = Usage(input_tokens=int(raw.get("prompt_tokens") or 0), source="provider")
        return data, usage
