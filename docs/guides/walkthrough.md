# Code walkthrough

A guided tour for contributors. Read [the LLD](../architecture/LLD.md) for the full detail.

## Repository

```
apps/api/            Python package: gateway, dashboard API, worker, mock LLM
  src/tokenshield/   one package per domain
  src/mockllm/       deterministic OpenAI and Anthropic stand-in for demos and tests
  tests/unit, tests/integration
apps/web/            Next.js dashboard
e2e/                 Playwright journeys
scripts/qa/          Puppeteer QA sweep
infra/terraform/     modules and the local-floci, aws-dev, aws-prod environments
infra/docker/        api and web images
deploy/compose/      local stack (Floci overlay, real-AWS overlay)
docs/                architecture, ADRs, guides, OpenAPI
```

## Follow one request

1. **`gateway/router.py`** receives `POST /v1/chat/completions`, parses JSON with a size cap
   and hands off to `GatewayService.chat`.
2. **`gateway/dependencies.py authenticate_key`** parses `tsk_<prefix>_<secret>`, looks the
   key up through the in-process `ConfigCache`, checks the peppered hash in constant time,
   and builds a `RequestContext` (project, end user, task id, cache headers, idempotency).
3. **`gateway/catalog.py`** is the gateway's read model: models with providers and current
   prices, projects, budgets and rules, loaded in a handful of queries and cached for 5 s.
4. **`gateway/service.py _admit`** resolves the model, estimates tokens
   (`gateway/tokens.py`), runs static rules (`policies/engine.py`), rewrites the output
   allowance, checks key limits (`limits/limiter.py`) and agent task caps
   (`policies/stateful.py`).
5. **`_cache_lookup`** builds the partitioned key (`cache/keys.py`) and runs the
   get-or-lead script (`cache/store.py`); a hit is served and accounted immediately.
6. **`_check_retry_storm`**, then **`_reserve`**: applicable budgets
   (`budgets/resolver.py`) are reserved atomically (`budgets/ledger.py`), rebuilding missing
   counters from Postgres.
7. **`_call`** goes through the provider adapter (`providers/adapters/openai.py` or
   `anthropic.py`), which classifies failures as not sent, uncertain or an error status.
8. **`_settle_success`** computes the actual cost (`pricing/engine.py`) and settles budgets,
   TPM, the usage record (`usage/recorder.py`) and the cache in one Redis pipeline.
9. **`worker.py`** drains the usage stream into Postgres, rolls up hours, settles uncertain
   requests and flushes statistics.

## Add a provider

Create `providers/adapters/<name>.py` implementing `ProviderAdapter` (`chat`,
`chat_stream`, `embeddings`), translating to and from the OpenAI shape and returning
`Usage`. Register it in `providers/adapters/registry.py` and `PROVIDER_KINDS`, add the kind
to `providers/schemas.py`, and add unit tests against `httpx.MockTransport` like
`tests/unit/providers/test_adapters_http.py`.

## Add a policy rule kind

Add the kind and its parameter schema to `policies/schemas.py` (`PARAMS`, `ACTIONS`),
implement it in `policies/engine.py` (static) or `policies/stateful.py` (needs state), add
the error code to the dashboard's `lib/chips.ts` labels, and cover it in
`tests/unit/policies` and `tests/integration/test_policies.py`.

## Add an admin endpoint

Domain `router.py` (HTTP only, role dependency `Viewer`, `Admin` or `Owner`), `schemas.py`,
`service.py` (rules plus `audit(...)` in the same transaction), and, if it changes gateway
behaviour, `await container.config_cache.invalidate()` after the write. Run `make openapi`
and `pnpm gen:api` in `apps/web` to refresh the typed client.
