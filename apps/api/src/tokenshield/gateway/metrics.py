"""Prometheus metrics for the gateway. Labels are bounded (model aliases and statuses are
admin-defined sets), never per-request values."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "tokenshield_requests_total",
    "Gateway requests by outcome",
    ["model", "status", "cache"],
)
REJECTIONS = Counter(
    "tokenshield_rejections_total",
    "Requests stopped before any upstream call, by rule",
    ["rule"],
)
TOKENS = Counter(
    "tokenshield_tokens_total",
    "Provider-billed tokens",
    ["model", "direction"],
)
COST = Counter(
    "tokenshield_cost_usd_total",
    "Provider spend in USD (actual, from provider usage where reported)",
    ["model"],
)
AVOIDED = Counter(
    "tokenshield_avoided_cost_usd_total",
    "Estimated provider spend avoided by cache hits and coalescing",
    ["model"],
)
UPSTREAM_LATENCY = Histogram(
    "tokenshield_upstream_latency_seconds",
    "Time spent waiting on the provider",
    ["model"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64),
)
OVERHEAD = Histogram(
    "tokenshield_gateway_overhead_seconds",
    "Time the gateway adds on top of the provider call",
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)
