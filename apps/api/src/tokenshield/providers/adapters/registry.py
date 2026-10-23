"""Adapter lookup by provider kind. Adding a provider = one adapter file + one line here."""

from __future__ import annotations

import httpx

from tokenshield.providers.adapters.anthropic import AnthropicAdapter
from tokenshield.providers.adapters.base import ProviderAdapter
from tokenshield.providers.adapters.openai import OpenAIAdapter

PROVIDER_KINDS = ("openai", "anthropic")


class AdapterRegistry:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._adapters: dict[str, ProviderAdapter] = {
            "openai": OpenAIAdapter(client),
            "anthropic": AnthropicAdapter(client),
        }

    def get(self, kind: str) -> ProviderAdapter:
        try:
            return self._adapters[kind]
        except KeyError:
            raise ValueError(f"unknown provider kind: {kind}") from None
