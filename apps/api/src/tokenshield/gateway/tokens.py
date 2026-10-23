"""Pre-call token estimation.

Uses tiktoken for OpenAI-family encodings. For other tokenizers the estimate is
characters / 4, rounded up, which overestimates English text slightly; that is the safe
direction for budget reservations. Every figure computed here is an estimate and is
replaced by provider-reported usage after the call.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import orjson
import tiktoken

TIKTOKEN_ENCODINGS = {"o200k_base", "cl100k_base"}
# Per-message framing overhead (role markers, separators) and reply priming, following
# OpenAI's published counting recipe for chat models.
TOKENS_PER_MESSAGE = 3
REPLY_PRIMING = 3
# A conservative flat charge per image part. Real cost depends on resolution and provider.
IMAGE_TOKENS = 1105


@lru_cache(maxsize=8)
def _encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def count_text(text: str, tokenizer: str) -> int:
    if not text:
        return 0
    if tokenizer in TIKTOKEN_ENCODINGS:
        return len(_encoding(tokenizer).encode(text, disallowed_special=()))
    return math.ceil(len(text) / 4)


def _content_tokens(content: Any, tokenizer: str) -> int:
    if isinstance(content, str):
        return count_text(content, tokenizer)
    total = 0
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                total += count_text(part.get("text", ""), tokenizer)
            elif part.get("type") in ("image_url", "input_image", "image"):
                total += IMAGE_TOKENS
            else:
                total += count_text(orjson.dumps(part).decode(), tokenizer)
    return total


def estimate_chat_input(body: dict[str, Any], tokenizer: str) -> int:
    total = REPLY_PRIMING
    for msg in body.get("messages") or []:
        total += TOKENS_PER_MESSAGE
        total += _content_tokens(msg.get("content"), tokenizer)
        if name := msg.get("name"):
            total += count_text(str(name), tokenizer) + 1
        if calls := msg.get("tool_calls"):
            total += count_text(orjson.dumps(calls).decode(), tokenizer)
    if tools := body.get("tools"):
        total += count_text(orjson.dumps(tools).decode(), tokenizer)
    fmt = body.get("response_format")
    if isinstance(fmt, dict) and fmt.get("type") == "json_schema":
        total += count_text(orjson.dumps(fmt).decode(), tokenizer)
    return total


def estimate_embedding_input(body: dict[str, Any], tokenizer: str) -> int:
    value = body.get("input")
    if isinstance(value, str):
        return count_text(value, tokenizer)
    if isinstance(value, list):
        return sum(count_text(v, tokenizer) if isinstance(v, str) else len(v) for v in value)
    return 0


def last_user_text(body: dict[str, Any]) -> str:
    for msg in reversed(body.get("messages") or []):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def warm_up() -> None:
    """Load encodings before serving traffic (first load reads the BPE files)."""
    for name in TIKTOKEN_ENCODINGS:
        _encoding(name)
