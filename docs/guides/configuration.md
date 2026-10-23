# Configuration reference

Every setting is an environment variable, read once at boot by `core/config.py` (pydantic
settings, case-insensitive). With `ENVIRONMENT=production` the API refuses to start on
unsafe values; see [security.md](../architecture/security.md#production-boot-guards).

## Runtime

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development`, `test` or `production`. Production enables the boot guards and blocks the demo seed |
| `TOKENSHIELD_CLOUD` | `local` | `local`, `floci` or `aws`. On `aws`, an `AWS_ENDPOINT_URL` override and `BUDGET_FAILURE_MODE=open` are refused |
| `LOG_LEVEL` | `INFO` | JSON log level |
| `PORT` | `4130` | Port for `tokenshield serve` (Compose uses 8080 inside the container) |
| `WEB_CONCURRENCY` | `2` | Uvicorn worker processes for `tokenshield serve` |

## Data stores

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://tokenshield:tokenshield@localhost:4142/tokenshield` | Postgres 16 with the `vector` extension. On AWS, `?ssl=require` |
| `REDIS_URL` | `redis://localhost:4179/0` | Redis 7 or Valkey. On AWS, `rediss://:<token>@host:6379/0` (TLS and auth). Run with AOF and `noeviction` |

## Security

| Variable | Default | Meaning |
| --- | --- | --- |
| `SESSION_SECRET` | development value | Signs dashboard sessions. 32+ random characters in production |
| `API_KEY_PEPPER` | development value | HMAC pepper for gateway key hashes. 32+ random characters, different from `SESSION_SECRET`. Changing it invalidates every gateway key |
| `SESSION_TTL_HOURS` | `12` | Dashboard session lifetime |
| `COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `CORS_ORIGINS` | `http://localhost:4110` | Comma-separated dashboard origins |
| `KEY_MODE` | `local` | How provider credentials are sealed: `local` (AES-256-GCM) or `kms` |
| `LOCAL_MASTER_KEY` | development value | Key material for `KEY_MODE=local`. 32+ characters in production |
| `KMS_KEY_ID` | `alias/tokenshield-local` | KMS key or alias for `KEY_MODE=kms` |
| `STORE_CONTENT` | `false` | Store short prompt excerpts on usage events and cache entries. Off keeps prompts out of the database |

## AWS and storage

| Variable | Default | Meaning |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Region for S3 and KMS |
| `AWS_ENDPOINT_URL` | unset | Emulator endpoint (Floci). Must be unset on real AWS |
| `S3_FORCE_PATH_STYLE` | `false` | Path-style S3 addressing (needed for Floci) |
| `S3_PUBLIC_ENDPOINT` | unset | Host used in presigned download links when the browser reaches S3 at a different address than the API (Compose) |
| `STORAGE` | `local` | Where report exports go: `local` or `s3` |
| `EXPORTS_BUCKET` | `tokenshield-local-exports` | S3 bucket for exports |
| `LOCAL_STORAGE_DIR` | `./.data/exports` | Directory for `STORAGE=local` (`/data/exports` in Compose) |

## Gateway behaviour

| Variable | Default | Meaning |
| --- | --- | --- |
| `UPSTREAM_TIMEOUT_S` | `60` | Provider timeout when the provider has none of its own |
| `BUDGET_FAILURE_MODE` | `closed` | With Redis unreachable: `closed` refuses requests under hard budgets (503); `open` lets them through unchecked |
| `DEFAULT_MAX_OUTPUT_TOKENS` | `1024` | Output allowance reserved when a request sets no `max_tokens` |
| `CACHE_DEFAULT_TTL_S` | `3600` | Cache TTL when a project has none |
| `COALESCE_WAIT_S` | `30` | How long identical requests wait for an in-flight leader |
| `UNCERTAIN_SETTLE_AFTER_S` | `900` | When the worker settles UNCERTAIN requests at their reserved worst case |
| `SEMANTIC_CACHE` | `false` | Enable the semantic cache (projects must also opt in) |
| `SEMANTIC_THRESHOLD` | `0.92` | Cosine similarity required for a semantic hit |
| `SEMANTIC_EMBEDDING_MODEL` | `embed-small` | Embedding model alias used for semantic lookups |

## Observability

| Variable | Default | Meaning |
| --- | --- | --- |
| `OTEL_ENABLED` | `false` | Export OpenTelemetry traces over OTLP/HTTP |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel default | Collector endpoint (standard OTel variable) |
| `OTEL_SERVICE_NAME` | `tokenshield-api` / `tokenshield-worker` | Standard OTel variable |

## Demo and tools

| Variable | Used by | Meaning |
| --- | --- | --- |
| `DEMO_PASSWORD`, `TS_DEMO_PASSWORD` | `seed-demo`, e2e, QA | Password for the demo accounts |
| `MOCK_LLM_URL` | `seed-demo`, bench | Where demo providers point (`http://mock-llm:4150` in Compose) |
| `TOKENSHIELD_API_URL` | `seed-demo`, bench | API base URL for live demo traffic |
| `TOKENSHIELD_OWNER_PASSWORD` | `create-owner` | Password, instead of an interactive prompt |

## Compose ports (`deploy/compose/.env`)

`TS_WEB_PORT` (4110), `TS_API_PORT` (4130), `TS_MOCK_LLM_PORT` (4150), `TS_PG_PORT` (4142),
`TS_REDIS_PORT` (4179), `TS_FLOCI_PORT` (4166), `TS_LOG_LEVEL`.
