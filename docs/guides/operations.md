# Operations

## Processes

| Process | Command | Scale |
| --- | --- | --- |
| API and gateway | `tokenshield serve` | Stateless; run as many replicas as traffic needs. Each keeps a 5 s config cache coordinated through Redis |
| Worker | `tokenshield worker` | Run at least one, two for resilience. Every worker drains the usage stream (consumer group); periodic jobs take a Redis lease so exactly one instance runs each |
| Dashboard | Next.js standalone server | Stateless |
| Migrations | `tokenshield migrate` | One-off before each release (ECS: the `migrate` task) |

### Worker jobs

| Job | Interval | Purpose |
| --- | --- | --- |
| `usage_drain` | continuous | Write buffered usage events to Postgres in batches of up to 500; reclaim entries a crashed worker left pending |
| `rollups` | 60 s | Recompute the last closed hours of `usage_rollups_hourly`, including reconciliation corrections |
| `reconcile` | 60 s | Settle UNCERTAIN requests older than `UNCERTAIN_SETTLE_AFTER_S` at their reserved worst case |
| `cache_flush` | 10 s | Move new cache entries and hit counters from Redis into `cache_entries` |
| `policy_flush` | 15 s | Move policy trigger counts into `policy_rules` |
| `cleanup` | 1 h | Delete cache metadata expired more than 7 days ago and expired semantic vectors |

If no worker runs, budgets are still enforced (counters live in Redis), but the request
log, analytics and cache statistics stop updating and the usage stream grows.

## Health

| Endpoint | Meaning |
| --- | --- |
| `GET /healthz` | Liveness: the process answers. Used by the ALB and container health checks |
| `GET /readyz` | Readiness: Postgres and Redis answer within 2 s. 503 with per-dependency detail otherwise |
| `GET /api/v1/system` | Deployment configuration and live checks (dashboard Settings page) |

## Metrics

`GET /metrics` exposes Prometheus metrics. Labels are bounded sets (model aliases,
statuses, rule codes), never per-request values.

| Metric | Type | Labels | Use |
| --- | --- | --- | --- |
| `tokenshield_requests_total` | counter | `model`, `status`, `cache` | Traffic and outcomes |
| `tokenshield_rejections_total` | counter | `rule` | Which rules and budgets are stopping traffic |
| `tokenshield_tokens_total` | counter | `model`, `direction` | Provider-billed tokens |
| `tokenshield_cost_usd_total` | counter | `model` | Provider spend |
| `tokenshield_avoided_cost_usd_total` | counter | `model` | Spend avoided by the cache and coalescing |
| `tokenshield_upstream_latency_seconds` | histogram | `model` | Provider latency |
| `tokenshield_gateway_overhead_seconds` | histogram | | Time the gateway adds on top of the provider |

Useful alerts: `rate(tokenshield_rejections_total{rule="budget_exceeded"}[5m])` above
normal, `budget_service_unavailable` rejections at all, p95 gateway overhead, and the
length of the Redis stream `ts:usage:stream` (a growing backlog means no worker).

Logs are JSON lines with a `request_id` (also returned as `x-request-id`). Each rejection
logs `"event": "budget_rejected"` or `"request_rejected"` with the rule. Traces: set
`OTEL_ENABLED=true` and the standard `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Routine tasks

- **Rotate a provider key:** Models, Providers, edit, paste the new key. It is sealed and
  live on every instance within about a second.
- **Rotate a gateway key:** create a new key, deploy it to the application, revoke the old
  one. Revocation is immediate.
- **Change a price:** Models, publish a new price version. New requests use it; recorded
  requests keep the version they were billed at.
- **Re-point a model alias** to a different upstream model: purge that project's cache
  afterwards if answers from the old model should not be reused.
- **Purge the cache:** Cache, Purge (all projects or one).
- **Rotate `SESSION_SECRET`:** signs everyone out. **Rotate `API_KEY_PEPPER`:** invalidates
  every gateway key; issue new keys first.

## Backups

Postgres holds everything durable: configuration, the usage ledger, the audit log. RDS
automated backups cover it. Redis holds budget counters (rebuilt from Postgres when
missing), cached bodies (disposable) and the usage stream (drained within milliseconds).
Run Redis with AOF so a restart does not lose the stream backlog.
