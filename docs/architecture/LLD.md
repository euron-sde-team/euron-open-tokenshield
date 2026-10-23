# Low-Level Design

This document walks the code: how the API is laid out, what each package owns, the gateway
pipeline step by step with the Redis commands each step issues, and what the worker does. The
system view is in [HLD.md](HLD.md); budgets and caching have their own deep dives in
[budgets.md](budgets.md) and [caching.md](caching.md). Paths are relative to
`apps/api/src/tokenshield/` unless they start with `apps/`, `infra/` or `deploy/`.

- [Repository layout](#repository-layout)
- [Layering](#layering)
- [core](#core)
- [Domain packages](#domain-packages)
- [The catalog read model](#the-catalog-read-model)
- [The request pipeline step by step](#the-request-pipeline-step-by-step)
- [Streaming](#streaming)
- [Embeddings and the Playground](#embeddings-and-the-playground)
- [Idempotency](#idempotency)
- [Provider adapters](#provider-adapters)
- [The worker](#the-worker)
- [Redis key reference](#redis-key-reference)
- [Timeouts, limits and constants](#timeouts-limits-and-constants)
- [Concurrency and idempotency guarantees](#concurrency-and-idempotency-guarantees)

## Repository layout

```
apps/api/                 FastAPI service, worker, CLI and the mock LLM (one Python package each)
  src/tokenshield/        the product
  src/mockllm/            deterministic OpenAI + Anthropic compatible upstream (demo and tests)
  tests/unit/             no network, no database
  tests/integration/      real Postgres, Redis and the mock upstream over HTTP
apps/web/                 Next.js 15 dashboard (App Router, TanStack Query, Tailwind v4)
deploy/compose/           compose.yaml + compose.floci.yaml (+ compose.aws.yaml)
infra/docker/             api.Dockerfile, web.Dockerfile
infra/terraform/          modules/ + envs/{local-floci,aws-dev,aws-prod}
scripts/                  gen-local-env.sh, test-db.sh, test-matrix.sh, check-sanitization.sh
docs/                     PLAN.md, architecture/, guides/, api/openapi.yaml
```

## Layering

The API is packaged by domain. Within a domain, dependencies point inward:

```
router.py     HTTP only: parse, authorize (role dependency), call the service, shape the response
schemas.py    Pydantic request and response models: the public contract, validated at the edge
service.py    business rules, transactions and audit rows; owns its SQLAlchemy queries
models.py     SQLAlchemy models owned by the domain
```

Services hold their own queries. There are no per-domain `repository.py` modules in 0.1.0;
`core/repository.py` defines a generic base that no domain uses yet. Two deliberate
cross-domain reads exist, both read-only and both on the gateway's hot path: the catalog
loader ([below](#the-catalog-read-model)) and the budget counter hydrator
(`budgets/resolver.py`, which sums `usage_events`, `reconciliation_events` and
`budget_reservations`).

Every admin mutation follows the same shape: the service changes rows, adds an `audit_log`
row in the same session (`audit/service.py audit`), commits, and the router then calls
`container.config_cache.invalidate()` when the change affects the gateway.

## core

| Module | Responsibility |
| ------ | -------------- |
| [`core/config.py`](../../apps/api/src/tokenshield/core/config.py) | `Settings` (pydantic-settings, every value from the environment) and `guard()`, the production boot guards. `get_settings()` is cached and calls the guard. Reference: [configuration.md](../guides/configuration.md) |
| [`core/container.py`](../../apps/api/src/tokenshield/core/container.py) | `Container`: the process-wide services built once in the app lifespan (database, Redis, HTTP client, `ConfigCache`, `BudgetLedger`, adapter registry, sealer, storage), held on `app.state` instead of module globals so tests build an isolated one per app |
| [`core/db.py`](../../apps/api/src/tokenshield/core/db.py) | Async engine (pool 10, overflow 20, pre-ping, recycle 1800 s), session factory, declarative `Base` |
| [`core/redis_client.py`](../../apps/api/src/tokenshield/core/redis_client.py) | One pooled client per process: 2 s socket and connect timeouts, health check every 15 s, no retry on timeout (a slow Redis must surface as an error, not as a hidden retry that doubles a reservation) |
| [`core/cache.py`](../../apps/api/src/tokenshield/core/cache.py) | `ConfigCache`: in-process TTL cache (5 s) with single-flight loading and cluster-wide invalidation through `ts:cfg:version` |
| [`core/security.py`](../../apps/api/src/tokenshield/core/security.py) | argon2 password hashing with a constant-time dummy for unknown users, password policy, HS256 session JWTs, API key generation, parsing and peppered HMAC |
| [`core/sealing.py`](../../apps/api/src/tokenshield/core/sealing.py) | `KeySealer` protocol: `LocalSealer` (AES-256-GCM) and `KmsSealer` (KMS with encryption context) |
| [`core/storage.py`](../../apps/api/src/tokenshield/core/storage.py) | `ObjectStorage` protocol: `LocalStorage` (path-traversal safe) and `S3Storage` (SSE-KMS, presigned GET through `S3_PUBLIC_ENDPOINT`) |
| [`core/aws.py`](../../apps/api/src/tokenshield/core/aws.py) | boto3 clients built from configuration only (endpoint, path style, standard retries); no emulator branches |
| [`core/errors.py`](../../apps/api/src/tokenshield/core/errors.py) | `AppError` hierarchy and the one place errors become JSON (`{"error": {code, type, message, details}}`, compatible with OpenAI SDK error parsing) |
| [`core/middleware.py`](../../apps/api/src/tokenshield/core/middleware.py) | Pure ASGI middleware (not `BaseHTTPMiddleware`, which buffers streams): request id, security headers, one log line per request |
| [`core/logs.py`](../../apps/api/src/tokenshield/core/logs.py) | JSON formatter with request id from a context variable and key-name redaction |
| [`core/money.py`](../../apps/api/src/tokenshield/core/money.py) | Integer nano-dollar helpers, always rounding up ([ADR-0003](adr/0003-integer-nano-dollars.md)) |
| [`core/deps.py`](../../apps/api/src/tokenshield/core/deps.py) | `ContainerDep`, `SessionDep`, client IP from `X-Forwarded-For` |
| [`main.py`](../../apps/api/src/tokenshield/main.py) | `create_app()`: routers, error handlers, GZip (over 2 KiB), CORS allowlist, request middleware; lifespan builds the container and preloads tiktoken encodings |
| [`cli.py`](../../apps/api/src/tokenshield/cli.py) | `tokenshield serve | worker | migrate | create-owner | seed-demo | openapi` |

## Domain packages

| Package | Owns | Notable details |
| ------- | ---- | --------------- |
| `auth` | Sign-in, sign-out, `/me`, password change, role dependencies | Lockout after 5 failures for 15 minutes; 20 sign-ins per minute per IP; password change bumps `session_version` |
| `users` | Dashboard users and roles | At least one active owner always; only an owner creates or changes an owner; role or disable changes bump `session_version` |
| `teams` | Teams | Only empty teams can be deleted |
| `projects` | Projects and their cache settings and model allowlist | `cache_ttl_s` 10 s to 30 days, default 3600 |
| `keys` | Gateway API keys | Plaintext shown once on creation; RPM, TPM, concurrency limits and expiry per key; revocation |
| `providers` | Providers, models, price versions | Provider key sealed on write, never returned (`has_key`, `key_hint` only); prices are immutable versions |
| `pricing` | `Price`, `worst_case_cost`, `actual_cost` | Pure functions |
| `budgets` | Budget CRUD and live status; `ledger.py` (Lua scripts), `resolver.py` (which counters apply, hydration), `windows.py` (UTC windows) | See [budgets.md](budgets.md) |
| `limits` | `Limiter`: sliding-window RPM and TPM, concurrency slots | Atomic Lua scripts |
| `policies` | Rule CRUD; `engine.py` static rules; `stateful.py` retry storms and agent task caps | See [waste-prevention.md](waste-prevention.md) |
| `cache` | `keys.py` (keys, eligibility), `store.py` (Redis cache and coalescing), `semantic.py` (pgvector), admin router | See [caching.md](caching.md) |
| `gateway` | Router, key authentication, catalog, `GatewayService`, token estimation, metrics | The pipeline below |
| `usage` | `recorder.py` (stream and direct writes), request log, `analytics.py`, CSV exports | |
| `alerts` | Budget threshold and policy alerts, deduplicated by key | |
| `audit` | Append-only audit trail written in the same transaction as the change | |
| `playground` | Runs a chat completion through the full pipeline as a project, without a key | |
| `system` | `/healthz`, `/readyz`, `/metrics`, `/api/v1/system` | |
| `demo` | `seed-demo`: configuration through the real services, backfilled history, live traffic through the gateway | Refuses to run with `ENVIRONMENT=production` |

## The catalog read model

The gateway needs models, prices, projects, budgets, policy rules and opened provider keys on
every request. Going through each domain's service would mean several queries per request.
Instead `gateway/catalog.py load_catalog` reads the other domains' tables directly, in a
handful of queries (one join for models and providers, one `DISTINCT ON` for the latest price
per model, one each for projects, budgets and rules), and builds an immutable `Catalog` of
frozen dataclasses (`ModelInfo`, `ProjectInfo`, `BudgetInfo`, `RuleInfo`).

This is the one sanctioned exception to "a domain reads another domain only through its
service": it is read-only, it is a snapshot, and every write path that affects it invalidates
it. The snapshot lives in `ConfigCache` under the key `catalog`; API keys are cached per prefix
under `key:<prefix>` so a lookup never loads every key.

Provider keys are opened once per sealed value: `_open_key` caches the plaintext under
`(provider_id, sha256(sealed_key))`, so a catalog refresh does not call KMS, and a rotated key
(new ciphertext, new digest) is opened on the first refresh after the rotation.

Writes that call `config_cache.invalidate()`: project create and update; provider create and
update; model create and update; new price versions; budget create, update and delete; policy
create, update and delete; key create, update and revoke; team delete.

## The request pipeline step by step

`gateway/router.py` reads the body (at most 8 MiB, must be a JSON object), copies the body's
`user` field into the end-user id when the `x-tokenshield-user` header is absent, and calls
`GatewayService.chat`. The numbers below follow the code in `gateway/service.py` and
`gateway/dependencies.py`.

### 1. Authenticate (`gateway/dependencies.py authenticate_key`)

1. Read `Authorization: Bearer tsk_...` (or `x-api-key`), split it into prefix and secret
   (`parse_api_key`: three parts, `tsk`, a 12-character prefix, a non-empty secret).
2. `ConfigCache.get("key:<prefix>")`. On a miss: one `SELECT` on `api_keys` by prefix.
3. HMAC-SHA256 the secret with `API_KEY_PEPPER` and compare in constant time. Check revoked,
   expired, and that the project is in the catalog (not archived).
4. Schedule `last_used_at` off the request path, at most once a minute per key.
5. Build `RequestContext`: request id (`req_` + 24 hex, or derived from the
   `Idempotency-Key`), project, key, end user, task id, cache header, cache scope. Header
   values are trimmed and cut to 200 characters.

Redis: `GET ts:cfg:version` at most once per second per process (inside `ConfigCache`);
`SET ts:keyused:<key_id> 1 NX EX 60` in the background task.

### 2. Resolve the model and estimate tokens (`_admit`)

`messages` must be a non-empty list. The alias must exist in the catalog with `kind=chat`
(else `404 model_not_found`). `gateway/tokens.py estimate_chat_input` counts with tiktoken for
`o200k_base` and `cl100k_base`, and `ceil(chars / 4)` for any other tokenizer, adding 3 tokens
of framing per message, 3 for reply priming, the JSON of tools, tool calls and `json_schema`
response formats, and a flat 1105 tokens per image part. Every figure here is an estimate and
is replaced by provider-reported usage after the call. Redis: none.

### 3. Static policies (`policies/engine.py evaluate_static`)

Pure function over `RequestFacts`. Computes the output allowance (requested
`max_completion_tokens` or `max_tokens`, else `DEFAULT_MAX_OUTPUT_TOKENS`, never above the
model's `max_output_tokens` or the room left in its context window), then applies the project
allowlist, restricted models, the context window, and every enabled rule of kind
`max_input_tokens`, `max_output_tokens`, `restricted_model` and `prompt_injection`. The body is
rewritten with the final allowance, and the worst-case estimate is priced on it. Alert-only
matches are queued as alerts. Redis: none.

### 4. Limits (`_check_limits`, `limits/limiter.py`)

Per API key, only when the key has the limit set:

| Limit | Redis |
| ----- | ----- |
| RPM | `EVALSHA` sliding-window script over `ts:rl:rpm:<key>:<minute>` and the previous minute: `GET`, `GET`, `INCRBY`, `EXPIRE` |
| TPM | Same script on `ts:rl:tpm:<key>:<minute>` with `amount = input estimate + output allowance`; trued up after the call |
| Concurrency | `EVALSHA` acquire on `ts:conc:key:<key>`: `INCR`, `EXPIRE`, `DECR` when over the limit |

Any `RedisError` here is `503 rate_limiter_unavailable`.

### 5. Agent task caps (`_stateful_checks`, `policies/stateful.py check_agent_task`)

Only when the request carries `x-tokenshield-task-id` and an `agent_task` rule applies. One
`EVALSHA` per rule on the hash `ts:task:<rule>:<project>:<task>` (`HGET` x5, `HSET`,
`EXPIRE`): checks calls, deadline, cost (spent plus this request's worst case) and repeated
identical tool calls, then counts the call. `RedisError` is `503 policy_service_unavailable`.

### 6. Cache lookup (`_cache_lookup`, `cache/store.py`)

Skipped when the request is not eligible (see [caching.md](caching.md#eligibility)).
Otherwise:

1. Compute the partition (project plus scope) and the exact key.
2. Non-streaming: `EVALSHA` get-or-lead: `GET ts:cache:body:<k>`, else
   `SET ts:cache:lock:<k> 1 NX PX <coalesce wait>`. One round trip answers "hit", "you lead"
   or "someone else leads". Streaming: a plain `GET` (streams are not coalesced).
3. On a miss with the semantic cache on: embed the last user turn through the configured
   embedding model and query `semantic_cache` (Postgres) for the nearest vector in the
   partition; a match above `SEMANTIC_THRESHOLD` is fetched with `GET`.
4. A follower polls: `GET` the body and `EXISTS` the lock with backoff from 20 ms to 250 ms,
   up to `COALESCE_WAIT_S`. If the lock disappears without a body, the follower tries
   `SET NX` to lead itself.

A hit returns here: one pipeline with `HINCRBY ts:cache:stats` (hits, tokens, avoided) and
`XADD ts:usage:stream`, then the response (replayed as SSE when the client asked to stream).
A Redis failure during lookup is a miss, never an error.

### 7. Retry storm (`_check_retry_storm`)

Only on the paid path, after the cache missed. For each applicable `retry_storm` rule:
`MULTI INCR ts:rs:<rule>:<key or project>:<end user>:<fingerprint>`, `EXPIRE ... NX`, `TTL`,
`EXEC`. Over the limit is `429 retry_storm` with `Retry-After` set to the key's remaining TTL.

### 8. Reserve (`_reserve`, `budgets/ledger.py`)

`budgets/resolver.py applicable` matches every enabled budget against the request's project,
team, key, end user and model, producing one counter key per budget. If a hard budget applies
and the model has no price, the request is refused with `422 model_unpriced`. Otherwise one
`EVALSHA` of the reserve script runs over all counter keys. If a counter is missing, the script
says which; the hydrator rebuilds it from Postgres and installs it with `SET NX` plus `EXPIRE`
(hydrate script), and the reservation is retried, at most 8 rounds. A refusal is
`402 budget_exceeded`; a `RedisError` is `503 budget_service_unavailable` unless
`BUDGET_FAILURE_MODE=open` or only soft budgets apply. Full detail in
[budgets.md](budgets.md).

### 9. Call the provider (`_call`, `providers/adapters`)

The adapter sends the rewritten body with the upstream model name and the opened provider key,
with the provider's timeout (or `UPSTREAM_TIMEOUT_S`). Outcomes:

| Outcome | Classified as | Accounting |
| ------- | ------------- | ---------- |
| Connect error, connect timeout, pool timeout | `UpstreamNotSentError` | Release the reservation, `ERROR` event, `502` |
| HTTP error status | `UpstreamHTTPError` | Release, `ERROR` event; status passed through for 400, 401, 403, 404, 409, 422, 429, otherwise `502` |
| Read timeout, write timeout, dropped connection, protocol error | `UpstreamUncertainError` | Keep the reservation and the TPM charge, `UNCERTAIN` event, `504 upstream_timeout` |
| Success | | Settle |

If the provider reports no usage, the gateway uses the input estimate and counts the output
text, and marks the record `usage_source=estimate`.

### 10. Settle (`_settle_success`)

`actual_cost(price, input, cached, output)` in nano-dollars, then one non-transactional
pipeline:

| Command | Purpose |
| ------- | ------- |
| `EVAL` adjust script on every counter key, delta `actual - reserved` | Replace the reservation with the real cost (skips counters that no longer exist) |
| `INCRBY ts:rl:tpm:<key>:<minute> (actual tokens - reserved tokens)` | TPM true-up |
| `XADD ts:usage:stream MAXLEN ~ 1000000 * r <record>` | The usage event and its reservation rows |
| `SET ts:cache:body:<k> <body> EX <ttl>` and `RPUSH ts:cache:new <meta>` | Store an eligible, cacheable answer |
| `DEL ts:cache:lock:<k>` | Release followers waiting on this key |

The adjust script is sent as plain `EVAL` on purpose: a registered script makes redis-py add a
`SCRIPT EXISTS` round trip to every pipeline execute. If the pipeline fails, the counters stay
at the reservation (the safe direction) and the record is written straight to Postgres.
Afterwards, off the response path: agent task cost is charged (`HINCRBY ... cost`) and budget
threshold alerts are evaluated (`MGET` on the counters, one deduplicated `INSERT` into
`alerts` when a threshold is crossed).

### 11. Finish (`_finish`, always runs)

Return unused TPM tokens if the request never settled (`INCRBY` negative), release the
concurrency slot (`EVALSHA` release: `DECR`, floor at zero), and drop the lead lock if this
request still holds it.

### Rejections

Any `AppError` raised before or during admission, reservation or the retry-storm check is
recorded as a `REJECTED` usage event (via `XADD`, falling back to Postgres) with the error code
in `rule`, counted in `tokenshield_rejections_total{rule}`, logged, and re-raised. The one
exception is `request_in_progress` (an idempotency conflict), which is not recorded.

## Streaming

`_stream` returns a `StreamingResponse` whose generator relays the adapter's SSE chunks. The
adapter fills a `StreamState` (text, finish reason, tool calls, provider usage) as chunks pass;
for OpenAI-compatible providers the gateway sets `stream_options.include_usage=true` so the
final chunk carries real token counts.

When the generator ends, for any reason, a `finalize` task runs under `asyncio.shield`, because
Starlette cancels the generator when the client disconnects and accounting must still
complete:

| Ending | Accounting |
| ------ | ---------- |
| Stream completed | Settle from provider usage (or the estimate); cache the joined text when the finish reason was `stop` and there were no tool calls |
| Upstream failed before any chunk | Same as a non-streaming failure; an SSE error event and `[DONE]` are sent to the client |
| Upstream failed after chunks were sent | `UNCERTAIN`, reservation held |
| Client disconnected mid-stream | `UNCERTAIN` with reason `client disconnected mid-stream`: the provider may keep generating and billing |

Streaming responses carry `x-tokenshield-estimated-cost-usd` but not the actual cost, because
headers are sent before the cost is known; the actual cost is on the usage event.

## Embeddings and the Playground

`/v1/embeddings` runs authentication, model resolution (`kind=embedding`), an input estimate,
limits and the budget reservation, then calls the adapter's `embeddings`. There is no output
allowance, no caching and no policy evaluation. The Anthropic adapter answers embeddings with
`400`, since that API has none.

`POST /api/v1/playground/chat` (admin role) builds a `RequestContext` for the chosen project
with no key and `source=playground`, then calls the same `GatewayService.chat`. Budgets,
static and stateful policies, caching and accounting all apply; per-key limits do not, because
there is no key.

## Idempotency

With an `Idempotency-Key` header the request id becomes `req_` plus the first 24 hex characters
of `sha256(project_id | key)`, so the same key in the same project always maps to the same
usage row.

1. `GET ts:idem:resp:<rid>`: a stored response is replayed with
   `x-tokenshield-idempotent-replay: true`. Nothing is recorded or reserved.
2. Otherwise `SET ts:idem:lock:<rid> 1 NX EX <upstream timeout + 60>`; if another request holds
   it, `409 request_in_progress`.
3. A successful non-streaming JSON response is stored for 24 hours, then the lock is released.
   Errors are not stored, so a retry after an error runs again.

Independently of the header, `usage_events.request_id` is unique and every insert uses
`ON CONFLICT DO NOTHING`, so a replayed stream batch can never double count.

## Provider adapters

`providers/adapters/base.py` defines the `ProviderAdapter` protocol: `chat`, `chat_stream` and
`embeddings`, all speaking the OpenAI shape on both sides. The registry
(`providers/adapters/registry.py`) maps a provider kind to an adapter; adding a provider is one
file and one line.

| Kind | Adapter | Notes |
| ---- | ------- | ----- |
| `openai` | `openai.py` | Any OpenAI-compatible base URL (OpenAI, Ollama, vLLM, LM Studio, Groq, Together, proxies). Reads `prompt_tokens_details.cached_tokens` as cached input |
| `anthropic` | `anthropic.py` | Translates to the Messages API (`anthropic-version: 2023-06-01`, `x-api-key`), maps stop reasons, tool calls and images, and counts `cache_read_input_tokens` as cached input and cache creation tokens as input |

`http.py` holds the shared client (at most 500 connections, 100 keep-alive, no redirects, HTTP/1.1)
and the failure classification. The connect timeout is `min(5 s, timeout)`. There is no
automatic retry: a retry after an uncertain failure could bill twice.

The deterministic mock upstream (`apps/api/src/mockllm/app.py`) speaks both APIs and honours
markers in the last user message: `[[slow:SECONDS]]`, `[[error:STATUS]]`, `[[tool]]`,
`[[long]]`, `[[drop]]`. `GET /stats` returns call counts; the tests use it to prove a request
never reached the provider.

## The worker

`tokenshield worker` (`worker.py`) runs one usage loop plus five leased jobs. Run as many worker
processes as you like: every one drains the stream through the consumer group, and each
periodic job takes `SET ts:worker:lease:<job> 1 NX EX <interval - 1>` so exactly one instance
runs it per interval.

| Job | Interval | What it does |
| --- | -------- | ------------ |
| `usage_drain` | continuous | `XREADGROUP GROUP recorders <host-pid> COUNT 500 BLOCK 1000` on `ts:usage:stream`, insert the batch (`usage_events` with `ON CONFLICT (request_id) DO NOTHING`, then `budget_reservations` only for rows that were new) in one transaction, then `XACK` and `XDEL`. Every 30 s, `XAUTOCLAIM` entries idle for 60 s from crashed consumers |
| `rollups` | 60 s | Recompute closed hours from two hours before the latest rolled hour (or from the first event) up to the open hour, with one idempotent `INSERT ... ON CONFLICT DO UPDATE` per hour that folds in reconciliation deltas |
| `reconcile` | 60 s | Find `UNCERTAIN` events older than `UNCERTAIN_SETTLE_AFTER_S` with no reconciliation, insert a reconciliation event with `delta = estimated_cost_nusd`, mark their reservations `settled` at the reserved amount; 500 per run |
| `cache_flush` | 10 s | `LRANGE`/`LTRIM` up to 1000 new entry records from `ts:cache:new` into `cache_entries` (upsert), and `RENAME` the `ts:cache:stats` hash aside to add hit counts without losing increments |
| `policy_flush` | 15 s | `RENAME` `ts:policy:hits` aside and add the counts to `policy_rules.triggered_count` |
| `cleanup` | 3600 s | Delete `cache_entries` that expired more than 7 days ago and expired `semantic_cache` rows |

On `SIGTERM` the worker stops after the current iteration; the container's `tini` forwards the
signal. A failed job is logged and retried at its next interval.

## Redis key reference

| Key | Type | Written by | TTL |
| --- | ---- | ---------- | --- |
| `ts:cfg:version` | string counter | Admin writes | none |
| `ts:keyused:<key_id>` | string | Gateway auth | 60 s |
| `ts:rl:rpm:<key_id>:<minute>`, `ts:rl:tpm:<key_id>:<minute>` | string counter | Limiter | 120 s |
| `ts:rl:login:<ip>:<minute>` | string counter | Sign-in | 120 s |
| `ts:conc:key:<key_id>` | string counter | Limiter | `2 x UPSTREAM_TIMEOUT_S + 30` s, refreshed on acquire |
| `ts:task:<rule>:<project>:<task>` | hash | Agent task script | 24 h, refreshed per call |
| `ts:rs:<rule>:<subject>:<fingerprint>` | string counter | Retry-storm check | rule `window_s` |
| `ts:bud:<budget>:<window>:<scope>` | string counter (nUSD) | Ledger | window end plus 1 day; none for `total` |
| `ts:cache:body:<sha256>` | string (`r` or `z` prefixed) | Settlement | project TTL |
| `ts:cache:lock:<sha256>` | string | Get-or-lead | `COALESCE_WAIT_S` |
| `ts:cache:stats` | hash | Cache hits | until the next flush |
| `ts:cache:new` | list | Settlement | until the next flush |
| `ts:policy:hits` | hash | Policy matches | until the next flush |
| `ts:usage:stream` | stream, group `recorders` | Gateway | entries deleted after commit; capped near 1,000,000 |
| `ts:idem:lock:<rid>`, `ts:idem:resp:<rid>` | string | Idempotency | `UPSTREAM_TIMEOUT_S + 60` s; 24 h |
| `ts:an:<query>` | string | Analytics | 10 s |
| `ts:worker:lease:<job>` | string | Worker | job interval minus 1 s |

## Timeouts, limits and constants

| Constant | Value | Where |
| -------- | ----- | ----- |
| Request body limit | 8 MiB | `gateway/router.py MAX_BODY_BYTES` |
| Header value length | 200 characters | `gateway/dependencies.py` |
| Config cache TTL, version check | 5 s, 1 s | `core/cache.py` |
| Default output allowance | 1024 tokens | `DEFAULT_MAX_OUTPUT_TOKENS` |
| Upstream timeout | 60 s (per provider override up to 600 s) | `UPSTREAM_TIMEOUT_S`, `providers.timeout_s` |
| Upstream connect timeout | `min(5 s, timeout)` | `providers/adapters/http.py` |
| Coalescing wait and lock TTL | 30 s | `COALESCE_WAIT_S` |
| Uncertain settle delay | 900 s | `UNCERTAIN_SETTLE_AFTER_S` |
| Reservation hydration rounds | 8 | `BudgetLedger.MAX_HYDRATE_ROUNDS` |
| Idempotent response retention | 24 h | `IDEMPOTENCY_TTL_S` |
| Usage stream cap | about 1,000,000 entries | `STREAM_MAXLEN` |
| Cache body compression threshold | 1024 bytes (zlib level 6) | `cache/store.py` |
| Analytics cache | 10 s | `usage/analytics.py CACHE_TTL_S` |
| Sign-in throttle, lockout | 20 per minute per IP; 5 failures, 15 minutes | `auth/router.py`, `auth/service.py` |
| Session lifetime | 12 h | `SESSION_TTL_HOURS` |
| Presigned export link | 300 s | `core/storage.py` |
| Readiness probe timeout | 2 s per dependency | `system/router.py` |
| Graceful shutdown | 30 s | `cli.py serve` |

## Concurrency and idempotency guarantees

| Concern | Mechanism | Proven by |
| ------- | --------- | --------- |
| Two requests overspending one budget | One Lua script checks every counter and increments all of them, atomically | `test_ac3_concurrent_requests_cannot_overspend` (50 parallel, budget fits 10, exactly 10 reach the upstream) |
| N identical requests calling the provider N times | `SET NX` lead lock; followers wait for the body | `test_ac7_identical_concurrent_requests_coalesce` |
| A failed leader stranding followers | Lead lock deleted on failure; a follower takes over | `test_failed_leader_releases_followers` |
| A worker crashing mid-batch | Entries stay pending until acked; `XAUTOCLAIM` hands them to a live worker | `test_usage_stream_survives_a_crashed_worker` |
| Redelivered usage double counting | Unique `request_id`, `ON CONFLICT DO NOTHING`, ledger rows only for new events | `test_recording_is_idempotent_by_request_id` |
| A client retry billing twice | `Idempotency-Key` lock and stored response | `test_idempotency_key_never_double_bills`, `test_idempotency_in_flight_conflict` |
| Two workers running the same sweep | Redis lease per job | `test_worker_loop_runs_jobs_once_per_lease_and_stops` |
| Ledger rows being edited after the fact | `BEFORE UPDATE OR DELETE` triggers on `usage_events`, `reconciliation_events`, `audit_log` | `test_usage_ledger_is_append_only` |
