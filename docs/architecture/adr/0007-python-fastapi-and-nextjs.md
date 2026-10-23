# ADR-0007: Python and FastAPI for the gateway, Next.js for the dashboard

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

The gateway lives in the LLM ecosystem: tokenizers (tiktoken), provider SDK conventions,
embeddings and evaluation tooling are Python first. The Euron open-source projects share a
standard: Python and FastAPI backends, Next.js frontends.

## Decision

The API, gateway and worker are one Python 3.12 package on FastAPI, Pydantic v2,
SQLAlchemy 2 (async, asyncpg), Alembic, redis-py and httpx, managed by uv and checked with
ruff and mypy `--strict`. The dashboard is Next.js 15 (App Router, React 19, TypeScript
strict, Tailwind, shadcn components, TanStack Query), proxying `/api` and `/v1` to the API
so the browser stays same-origin.

## Consequences

**Good**
- tiktoken and the provider wire formats are first-class.
- Async I/O end to end on the request path; blocking SDKs (boto3) run in threads.
- Typed contracts both sides: the dashboard's types are generated from the OpenAPI
  document, which a test keeps in sync with the app.

**Bad / caveats**
- Python's per-request CPU cost is higher than Go or Rust. The hot path is designed to be
  I/O bound (a few Redis round trips, no database), and the API scales horizontally.

## Alternatives considered

- **Go.** Faster per request, weaker ecosystem fit for tokenizers and providers.
- **A plain React SPA.** Next.js gives routing, code splitting and a same-origin proxy.
