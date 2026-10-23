# Euron TokenShield 0.1.0: build plan

A self-hosted AI gateway that sits between applications and LLM providers. It tracks every
token, enforces hard budgets **before** the upstream call, reuses eligible cached responses,
and blocks wasteful requests. One OpenAI-compatible endpoint, central policies,
provider-independent telemetry.

Source brief: the "Euron TokenShield Detailed Project Blueprint" (Oct 2026). 0.1.0 is
"TokenShield Core" from that brief, plus the waste controls its MVP checklist requires.

## Purpose

Teams shipping LLM features get surprise bills: one buggy agent loop, a retry storm or a
leaked key can burn a month of budget overnight, and provider dashboards only report it
afterwards. **TokenShield is a shield, so it must stop spend before it happens**, not chart
it later. Every request passes through one OpenAI-compatible endpoint where it is
attributed, priced, checked against hard budgets and waste rules, served from cache when
safely possible, and only then forwarded. Platform and finance teams get one place to set
limits and see exactly what was spent and what was avoided.

Comparable products: LiteLLM proxy, Portkey, Helicone, Cloudflare AI Gateway, Kong AI
Gateway. Most track spend after the fact or check budgets with a read-then-call race.
TokenShield's angle: **provably atomic hard budgets under concurrency**, privacy-scoped
caching that never crosses tenants or users, agent-loop and retry-storm containment, and
cost analytics that separate actual spend from avoided spend.

## Acceptance criteria (each is an automated test)

1. An unmodified OpenAI SDK client works by changing only `base_url` and `api_key`
   (streaming and non-streaming).
2. A request whose worst-case cost exceeds the remaining hard budget is rejected with a
   structured 402 **and the upstream receives zero calls**.
3. 50 concurrent requests against a budget that fits 10: exactly 10 reach the upstream and
   recorded spend never exceeds the limit.
4. Every successful request records input, cached and output tokens, model, provider,
   latency and cost with the price version used; an unpriced model is flagged, never free.
5. An identical eligible request is served from cache with zero upstream calls, and the
   dashboard reports the spend avoided.
6. A request from user A is never served user B's cached response when scoped by user, and
   requests marked sensitive bypass the cache.
7. N identical concurrent requests are coalesced into one upstream call.
8. A retry storm is throttled and an agent loop is stopped at its configured call or cost
   cap, with an error naming the limit.
9. An upstream timeout leaves the request `UNCERTAIN` with its reservation held, then
   reconciled by the sweep; it is never recorded as zero cost.
10. With Redis down, hard-budget requests fail closed (503), never pass unchecked.
11. Admins see usage, rejections, cache hits and savings in the dashboard and export a CSV.
12. `make up` starts the whole system (Postgres, Redis, Floci, mock upstream, api, worker,
    web) with Terraform applied against Floci.

## Caching layers

| Layer | What | Where | Key | TTL / invalidation |
| --- | --- | --- | --- | --- |
| Response cache | Chat completion bodies | Redis | SHA-256 of normalized request + scope | Project TTL; manual purge per entry/project |
| Semantic cache | Prompt embeddings | Postgres pgvector | partition (project, model, scope) | Same TTL; purged with the exact entry |
| Gateway config | API key lookup, project, models, prices, budgets, rules | In-process TTL cache (5s) backed by Redis version stamp | `cfg:v` counter | Any admin write bumps the version; every instance refreshes on next request |
| Budget counters | Spent + reserved per budget window | Redis | `bud:{id}:{window}` | Expire at window end; rehydrated from Postgres if missing |
| Analytics | Dashboard aggregates | Postgres `usage_rollups_hourly` (worker maintained) + Redis 15s response cache | query params | Rollups refreshed every minute; raw events only for the current hour |
| Dashboard | Server state | TanStack Query | per resource | `staleTime` per view, invalidated on mutation |

## Scope

### In 0.1.0

| Area | What ships |
| --- | --- |
| Gateway | `POST /v1/chat/completions` (OpenAI-compatible, streaming and non-streaming), `GET /v1/models`, `POST /v1/embeddings` passthrough. Auth by gateway API key (`tsk_<prefix>_<secret>`, stored as peppered HMAC). |
| Providers | Adapters: `openai` (any OpenAI-compatible base URL: OpenAI, Ollama, vLLM, LM Studio, Groq), `anthropic` (native Messages API, translated), `mock` (deterministic, for demos and tests). Provider keys sealed with KMS (Floci locally) and stored in Postgres; never returned by the API. |
| Model catalog | Model aliases map to provider + upstream model. Versioned pricing catalog (input, cached input, output per 1M tokens). Usage rows keep the pricing version id. Unknown pricing is flagged `UNPRICED`, never treated as free. |
| Token tracking | Pre-call estimate with `tiktoken` (documented fallback estimator for other providers, marked as estimate). Post-call provider-reported input, output and cached tokens. Append-only `usage_events` with request id, org/team/project/user/key attribution, model, provider, tokens, estimated cost, actual cost, cache status, latency, status, pricing version. Idempotent by request id; corrections are separate reconciliation events. |
| Budgets | Scopes: org, team, project, user (end-user id header), API key, model. Periods: daily, weekly, monthly, total. Modes: hard (block) and soft (alert). **Atomic reservation** of worst-case cost across every applicable budget in one Redis Lua script, mirrored to a Postgres reservation ledger; reconcile to actual cost; release on failure; `UNCERTAIN` status on upstream timeout (reservation held until reconciled, never assumed zero). Fail closed when Redis is unavailable for hard budgets. |
| Limits | Per-request max input tokens, max output tokens (cap or reject), RPM, TPM, concurrency per key/project. HTTP 429 with `Retry-After` and a structured error body naming the limit. |
| Caching | Exact-match cache in Redis: SHA-256 over normalized model, messages, tools, response format, sampling params, tenant scope and an optional `x-tokenshield-cache-scope` (user or context version). Eligibility rules: off for `temperature > 0` unless the project opts in, off for requests marked sensitive (`x-tokenshield-cache: off`), off when tools return calls. TTLs, manual invalidation, request **coalescing** of identical in-flight requests. Cache hits still pass auth, rate limits and policy, are logged, and report "spend avoided". |
| Waste prevention | Policy engine with rules: oversized prompt, excessive output, duplicate in-flight (coalesce), retry storm (same fingerprint N times in window), agent task caps via `x-tokenshield-task-id` (max calls, max cost, max consecutive identical tool calls, deadline), restricted models per project. Each rule: action `reject` / `cap` / `throttle` / `alert`. |
| Semantic cache | Behind `SEMANTIC_CACHE=true` (off by default): pgvector index of prompt embeddings, cosine threshold, same eligibility and scope rules as exact cache. |
| Analytics | Spend, tokens, cache hit rate, rejected requests, provider and model breakdown, top projects/keys, spend avoided, time series. CSV export written to S3 (Floci locally) with a presigned download. |
| Dashboard (Next.js) | Sign-in, Overview, Requests (live log with filters and detail drawer), Budgets, Policies, API keys, Providers and models (pricing), Projects and teams, Cache, Reports, Audit log, Settings. Dark and light. Built-in Playground to send a request through the gateway. |
| Admin API | Everything the dashboard does, under `/api/v1`, OpenAPI documented. Admin auth: email + password (argon2), JWT session cookie, roles `owner`, `admin`, `viewer`. |
| Ops | `/healthz`, `/readyz` (Postgres, Redis), Prometheus `/metrics`, OpenTelemetry tracing hooks (exporter optional), JSON logs, append-only audit log. |
| IaC | Terraform modules: network, database (RDS Postgres + pgvector), cache (ElastiCache Redis), storage (S3 exports), kms, secrets, ecr, service (ECS Fargate api + web behind ALB), observability. Envs: local-floci (S3, KMS, Secrets Manager applied against Floci), aws-dev, aws-prod (validate only). |

### Roadmap (not 0.1.0)

Measured model routing, context compression, approval workflows for restricted models,
OIDC/SSO, Kubernetes Helm chart, more native provider adapters, client SDKs beyond the
OpenAI-compatible surface, multi-region budget coordination.

## Request lifecycle

1. Authenticate API key, resolve org, project, team, key, end user, model alias.
2. Estimate input tokens; compute max output (request value capped by policy).
3. Policy engine pre-checks (size, output, restricted model, rate/TPM/concurrency, retry
   storm, agent task caps).
4. Cache lookup (exact, then semantic if enabled). Hit: record `HIT` usage event with
   avoided cost, return.
5. Coalesce if an identical eligible request is in flight.
6. Reserve worst-case cost atomically across all applicable budgets. Reject if any hard
   budget would be exceeded (no upstream call).
7. Call provider (timeout, no automatic retry that double bills).
8. Read actual usage, compute cost from the pricing version, reconcile reservation, write
   usage event, store eligible response in cache.
9. On timeout: event `UNCERTAIN`, reservation kept until reconciled by a background sweep.

## Code layout (domain packages)

`core/` (config, db, redis, errors, security, logging, deps, cache) and one package per
domain: `auth`, `users`, `teams`, `projects`, `keys`, `providers` (catalog + adapters),
`pricing`, `budgets`, `limits`, `policies`, `cache`, `gateway`, `usage` (events,
rollups, analytics, exports), `alerts`, `audit`, `health`. Each has router, schemas,
service, repository, models. Single-tenant deployment (one organisation per install), see
ADR.

## Data model (Postgres)

`teams`, `projects`, `users` (dashboard admins), `api_keys`, `providers`,
`models`, `pricing_versions`, `model_prices`, `budgets`, `budget_reservations`,
`usage_events` (append-only, trigger enforced), `reconciliation_events`, `policy_rules`,
`agent_tasks`, `cache_entries` (metadata and stats; bodies live in Redis),
`semantic_cache` (pgvector), `usage_rollups_hourly`, `alerts`, `exports`, `audit_log` (append-only).

## Ports (project 01)

web 4110, api 4130, postgres 4142, redis 4179, floci 4166, mock LLM 4150.

## Test plan

- Unit: cost engine (cached-input pricing, unpriced flag, versioning), token estimator,
  cache key normalization and eligibility, policy rules, budget period windows, API key
  hashing, config boot guards, provider request/response translation (Anthropic), SSE
  stream accounting.
- Integration (real Postgres, Redis, Floci, mock upstream): every admin endpoint with RBAC;
  gateway happy path; **concurrency: 50 parallel requests against a budget that fits 10,
  exactly 10 succeed and spend never exceeds the limit**; exhausted budget rejects with zero
  upstream calls; cache hit makes zero upstream calls; sensitive requests bypass cache;
  coalescing makes one upstream call for N identical in-flight; retry storm throttles;
  agent loop stops; upstream 500 releases reservation; upstream timeout marks UNCERTAIN and
  the sweep reconciles; Redis down fails closed for hard budgets; idempotent request id
  does not double count; KMS sealing of provider keys; S3 export.
- E2E (Playwright): sign in, create project, key, budget, send traffic via Playground,
  watch requests appear, hit the budget and see the rejection, cache hit shows savings,
  export a report.
- Browser QA (Puppeteer): every page, light and dark, desktop and phone.

## Release verification (0.1.0)

Every acceptance criterion is proven by an automated test (integration tests run against
real Postgres, Redis and the mock provider over HTTP; e2e against the full Compose stack).

| # | Criterion | Proven by |
| --- | --- | --- |
| 1 | Unmodified OpenAI SDK works | `test_gateway.py::test_ac1_unmodified_openai_sdk_non_streaming`, `..._streaming`, `test_ac1_sdk_lists_models_and_embeds` |
| 2 | Over-budget request refused with zero upstream calls | `test_budgets.py::test_ac2_exhausted_budget_rejects_with_zero_upstream_calls`; e2e `02-shield` |
| 3 | 50 concurrent requests, budget fits 10: exactly 10 reach upstream | `test_budgets.py::test_ac3_concurrent_requests_cannot_overspend` |
| 4 | Full accounting with price version; unpriced flagged | `test_gateway.py::test_ac4_*` (3 tests), `test_admin.py::test_new_price_applies_to_new_requests_only` |
| 5 | Cache hit with zero upstream calls, savings reported | `test_cache.py::test_ac5_*` (2 tests); e2e `02-shield`, `03-playground` |
| 6 | No cross-user or cross-project cache leaks; sensitive bypass | `test_cache.py::test_ac6_*` (3 tests), `test_semantic_cache_respects_context` |
| 7 | Identical concurrent requests coalesced | `test_cache.py::test_ac7_identical_concurrent_requests_coalesce` |
| 8 | Retry storms throttled, agent loops stopped, output capped | `test_policies.py::test_ac8_*` (3 tests) and agent cost, loop and limit tests |
| 9 | Timeout is UNCERTAIN, held, reconciled, never zero | `test_reliability.py::test_ac9_timeout_is_uncertain_and_holds_reservation` |
| 10 | Redis down: hard budgets fail closed | `test_budgets.py::test_ac10_redis_down_fails_closed_for_hard_budgets` |
| 11 | Dashboard shows usage, rejections, savings; CSV export | `test_analytics.py::test_ac11_export_csv` and analytics tests; e2e `02-shield`, `04-reports-and-roles` |
| 12 | `make up` starts everything with Terraform on Floci | Compose stack brought up from scratch, seeded, e2e and QA run against it; option matrix on its Floci |
