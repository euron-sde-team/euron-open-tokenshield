# Testing

TokenShield has seven layers of automated checks. Each proves something different.

| Layer | Command | Needs | Proves |
| --- | --- | --- | --- |
| Static | `make lint typecheck` | uv, pnpm | ruff, mypy `--strict`, ESLint and TypeScript strict across the API and dashboard |
| Unit (131) | `make test` | uv, pnpm | Pure logic: 104 API tests (pricing, budgets, policies, cache keys, tokens, adapters, security, config) and 27 dashboard tests (formatting, errors, roles, components) |
| Integration (82) | `make test-integration` | Docker | The real API in-process against real Postgres and Redis, with the mock provider over real HTTP |
| Option matrix (4 runs) | `make test-matrix` | `make up` (Floci) | The integration suite under every key and storage backend: local or KMS, local disk or S3 |
| Browser e2e (11) | `make e2e` | `make up && make demo` | User journeys through the real dashboard, gateway, API and mock provider |
| Browser QA | `make qa` | `make up && make demo` | Every page in light and dark, desktop and phone: no console errors, failed requests, broken images, error states or overflow |
| Infrastructure | `make tf-validate tf-lint tf-security sanitize` | Docker | Terraform validity for three environments, tflint, checkov, and no secrets, cloud identifiers or em/en dashes in the tree |
| AWS on Floci | `make tf-aws-on-floci` | Docker | The full `aws-dev` environment (148 resources) plans, applies, converges and destroys against an AWS API |

## Unit tests

```bash
make test
```

No database, no network. Provider adapters are tested against an in-memory HTTP transport.
A drift test fails if `docs/api/openapi.yaml` no longer matches the app (`make openapi`
regenerates it).

## Integration tests

```bash
make test-integration
```

Starts the Compose Postgres and Redis if needed (`scripts/test-db.sh`) and runs
`apps/api/tests/integration` against `tokenshield_test` and Redis database 15. A guard
refuses any database whose name lacks `test`, or a non-local host unless
`ALLOW_REMOTE_TEST_DB=true`, because the suite truncates every table. The mock LLM runs in
a background thread on a free port; tests read its call counter to prove that refused and
cached requests never reached the provider.

| File | Tests | Proves |
| --- | --- | --- |
| `test_gateway.py` | 13 | An unmodified OpenAI SDK works (streaming, models, embeddings); every success is fully accounted with the price version; cached input priced separately; unpriced models flagged; the Anthropic adapter end to end; bad and revoked keys |
| `test_budgets.py` | 9 | A refused request makes zero upstream calls; 50 concurrent requests cannot overspend a budget that fits 10; reservations settle to actual; soft budgets alert; per-user budgets; counters rebuild after Redis loss; fail closed and fail open |
| `test_cache.py` | 11 | Cache hits with zero upstream calls and reported savings; stream replay; user and project isolation; sensitive and sampled requests bypass; tool calls not cached; coalescing; failed leaders release followers; invalidation and purge |
| `test_policies.py` | 13 | Retry storms throttled but not for cache hits or other users; agent call, cost and loop caps; output capping; prompt size; restricted models and allowlists; alert-only rules; trigger counts; RPM, TPM and concurrency limits |
| `test_reliability.py` | 10 | Timeouts become UNCERTAIN and are settled at worst case; errors release reservations; idempotency keys; append-only ledger; a crashed worker's stream entries are reclaimed; Redis outage records directly to Postgres |
| `test_admin.py` | 13 | Sign-in, CSRF, lockout, password change ends sessions, viewer and admin permissions, owner guards, every resource's CRUD and audit, price versions, health, metrics, playground |
| `test_analytics.py` | 6 | Overview, breakdowns and time series; rollups agree with raw events; request log filters and keyset pagination; CSV export and formula-injection defence; analytics caching |
| `test_semantic_and_worker.py` | 4 | Semantic hits for reworded questions and never across contexts; alert acknowledgement; worker leases |
| `test_aws_backends.py` | 3 | KMS sealing with encryption context; S3 put, get and presigned download; exports landing in S3 (matrix only) |

## Option matrix

```bash
make up
make test-matrix
```

Runs the integration suite four times: keys `local` or `kms`, storage `local` or `s3`,
against Floci with the `local-floci` Terraform applied.

## Browser end-to-end tests

```bash
make up && make demo
make e2e
```

Playwright (Chromium) signs in once in global setup and reuses the session, because the
dashboard throttles sign-ins per IP. Suites: authentication; the core journey (create a
project, key and hard budget in the UI, call the gateway like an application, see the
request accounted and cached, then see the overspending request blocked); the playground
(cache result and policy rejection); CSV export and download; viewer permissions; policies.

## Browser QA sweep

```bash
make qa
```

`scripts/qa/qa.mjs` (Puppeteer) visits every page in light and dark at 1440x900 and
390x844, saves full-page screenshots to `scripts/qa/output/`, and fails on console errors,
failed or 4xx/5xx requests, broken images, rendered error states and horizontal overflow.
The screenshots are reviewed by a person before a release; the README captures come from
this run.

## AWS environment on Floci

```bash
make tf-aws-on-floci
```

`terraform validate` checks syntax and types, not what happens at plan and apply time. This
target copies `infra/terraform` to a temp directory, points the unmodified `aws-dev`
environment at a throwaway Floci with a provider override, requests a certificate from
Floci's ACM, then runs plan, apply, a second plan and destroy. The second plan may show
in-place updates for attributes Floci does not persist; any addition or replacement fails
the run. The ECR repositories are removed from state before the destroy: Floci deletes
repositories only when it can reach a backing registry container, which needs the Docker
socket, and the script does not give the emulator that access. It takes about five minutes.

## Benchmark

```bash
make up && make demo
make bench
```

Sends the same requests straight to the mock provider and through the gateway (with a
hard budget applied) and reports p50 and p95 latency, throughput and gateway overhead.
