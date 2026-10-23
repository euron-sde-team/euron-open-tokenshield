"""Cache keys and eligibility. Pure functions, exhaustively unit tested.

A cache key must change whenever anything that could change the answer, or who may see
it, changes. It covers the model alias, every generation parameter, the full message
list, tools and output schema, and a **partition**: the project plus an optional
caller-declared scope (an end user, a permission group, a document version). Two users
only share an entry when the caller says their context is shareable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import orjson

# Parameters that change the output. Anything else (user, metadata, stream flags) does not.
_KEYED_PARAMS = (
    "temperature",
    "top_p",
    "max_tokens",
    "max_completion_tokens",
    "stop",
    "seed",
    "n",
    "presence_penalty",
    "frequency_penalty",
    "logit_bias",
    "logprobs",
    "top_logprobs",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "response_format",
    "reasoning_effort",
)

CACHE_OFF_VALUES = {"off", "no-store", "false", "0", "bypass"}


@dataclass(frozen=True, slots=True)
class Eligibility:
    eligible: bool
    reason: str


def partition(project_id: str, scope: str | None) -> str:
    raw = f"{project_id}|{scope or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _canonical_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            content = content.strip()
        out.append(
            {
                "role": m.get("role"),
                "content": content,
                "name": m.get("name"),
                "tool_calls": m.get("tool_calls"),
                "tool_call_id": m.get("tool_call_id"),
            }
        )
    return out


def exact_key(body: dict[str, Any], alias: str, part: str) -> str:
    material = {
        "v": 1,
        "model": alias,
        "partition": part,
        "messages": _canonical_messages(body.get("messages") or []),
        "params": {k: body.get(k) for k in _KEYED_PARAMS if body.get(k) is not None},
    }
    return hashlib.sha256(orjson.dumps(material, option=orjson.OPT_SORT_KEYS)).hexdigest()


def semantic_partition(body: dict[str, Any], alias: str, part: str) -> str:
    """Everything except the final user turn must match exactly for a semantic hit.

    Only the last user message is compared by embedding; the system prompt, earlier turns,
    tools and parameters are hashed into the partition so a similar question in a
    different context can never match.
    """
    messages = body.get("messages") or []
    idx = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    context = messages[:idx] if idx >= 0 else messages
    material = {
        "v": 1,
        "model": alias,
        "partition": part,
        "context": _canonical_messages(context),
        "params": {k: body.get(k) for k in _KEYED_PARAMS if body.get(k) is not None},
    }
    return hashlib.sha256(orjson.dumps(material, option=orjson.OPT_SORT_KEYS)).hexdigest()[:32]


def request_fingerprint(body: dict[str, Any], alias: str) -> str:
    """Identity of a request regardless of scope, used for retry-storm detection."""
    return exact_key(body, alias, "")[:32]


def check_eligibility(
    body: dict[str, Any],
    *,
    project_cache_enabled: bool,
    allow_nondeterministic: bool,
    header: str | None,
) -> Eligibility:
    if header and header.strip().lower() in CACHE_OFF_VALUES:
        return Eligibility(False, "disabled by request header")
    if not project_cache_enabled:
        return Eligibility(False, "caching disabled for project")
    if (body.get("n") or 1) > 1:
        return Eligibility(False, "multiple choices requested")
    if body.get("logprobs"):
        return Eligibility(False, "logprobs requested")
    # OpenAI's default temperature is 1, so an absent temperature means sampled output.
    temperature = body.get("temperature", 1)
    if temperature not in (0, 0.0) and not allow_nondeterministic:
        return Eligibility(False, "sampled output (temperature > 0)")
    return Eligibility(True, "eligible")


def response_cacheable(body: dict[str, Any]) -> bool:
    """Only complete text answers are stored. Tool calls drive agent state, so replaying one
    could hide a loop; truncated or filtered answers are not worth reusing."""
    choices = body.get("choices") or []
    if len(choices) != 1:
        return False
    choice = choices[0]
    message = choice.get("message") or {}
    return (
        choice.get("finish_reason") == "stop"
        and not message.get("tool_calls")
        and isinstance(message.get("content"), str)
    )
