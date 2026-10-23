"""The contract every LLM provider adapter implements.

Adapters speak the OpenAI chat-completions shape on both sides: they receive an OpenAI-style
request body and return an OpenAI-style response (or SSE chunks), translating to and from
the provider's native API internally. The gateway never branches on provider kind.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class Usage:
    """Token counts. ``input_tokens`` includes ``cached_input_tokens``."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    source: str = "provider"  # provider | estimate


@dataclass(frozen=True, slots=True)
class UpstreamTarget:
    """Everything an adapter needs to make one call."""

    base_url: str
    api_key: str | None
    upstream_model: str
    timeout_s: float


@dataclass(slots=True)
class ChatResult:
    body: dict[str, Any]
    usage: Usage
    upstream_id: str | None = None


@dataclass(slots=True)
class StreamState:
    """Filled in by an adapter while a stream is consumed; read once it ends."""

    usage: Usage | None = None
    text: list[str] = field(default_factory=list)
    finish_reason: str | None = None
    tool_calls: bool = False
    response_id: str | None = None
    created: int | None = None


class UpstreamHTTPError(Exception):
    """The provider answered with an error status."""

    def __init__(self, status: int, message: str, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.body = body


class UpstreamNotSentError(Exception):
    """The request never reached the provider (connect error). Nothing can be billed."""


class UpstreamUncertainError(Exception):
    """The request was sent but no answer arrived. The provider may still bill it."""


class ProviderAdapter(Protocol):
    kind: str

    async def chat(self, target: UpstreamTarget, body: dict[str, Any]) -> ChatResult: ...

    def chat_stream(
        self, target: UpstreamTarget, body: dict[str, Any], state: StreamState
    ) -> AsyncIterator[bytes]:
        """Yield OpenAI-format SSE lines (``data: {...}\\n\\n``), ending with ``[DONE]``."""
        ...

    async def embeddings(
        self, target: UpstreamTarget, body: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]: ...
