# Threat model

Scope: the gateway and dashboard API, the worker, Redis, Postgres, the AWS resources the
Terraform creates, and the dashboard. Method: STRIDE per asset, with the mitigation that
exists in this repository and the residual risk.

## Assets

1. **Provider credentials** (direct financial exposure).
2. **Budget integrity** (the core promise: no upstream call beyond a hard limit).
3. **Cached responses** (may contain one user's or one project's private context).
4. **Gateway keys and dashboard sessions.**
5. **The usage ledger and audit log** (finance and forensics rely on them).
6. **Prompts and outputs in transit.**

## Threats and mitigations

| # | Threat (STRIDE) | Asset | Mitigation | Residual risk |
| --- | --- | --- | --- | --- |
| T1 | Spoofing: stolen gateway key used from elsewhere | 4, 2 | Keys scoped to one project, per-key RPM/TPM/concurrency limits, per-key budgets, expiry, instant revocation, last-used tracking | A stolen key works until revoked; budgets cap the damage |
| T2 | Spoofing: dashboard credential stuffing | 4 | argon2id, lockout after 5 failures, per-IP throttle, uniform timing for unknown emails | No built-in second factor in 0.1.0 (roadmap: SSO) |
| T3 | Tampering: concurrent requests race past a hard budget | 2 | Atomic Lua reservation across all counters; proven by a 50-concurrent-request test | None known in normal operation |
| T4 | Tampering: client times out on purpose so calls are recorded as free | 2, 5 | Sent-but-unanswered requests are UNCERTAIN, keep their reservation, and are settled at worst case | Conservative overcharge of uncertain calls |
| T5 | Tampering: retries double count or double bill | 5, 2 | Unique `request_id`, idempotent inserts, `Idempotency-Key` replay without a second provider call | Clients that do not send Idempotency-Key may retry a paid call themselves |
| T6 | Tampering: editing usage history | 5 | Append-only triggers on usage, reconciliation and audit tables; corrections are new rows | A database superuser can disable triggers; restrict that role |
| T7 | Information disclosure: provider keys read from the API, logs or database | 1 | Write-only API fields, KMS sealing with encryption context, log redaction, decrypted values only in process memory | Memory of a compromised API host |
| T8 | Information disclosure: one user served another's cached answer | 3 | Partitioned cache keys (project, optional user or context scope); user scope without a user id disables caching; semantic partitions include the full context | Callers who choose project scope for user-specific prompts; documented in [caching.md](caching.md) |
| T9 | Information disclosure: spend data via `/metrics` | 5 | ALB restricts `/metrics` to allowed CIDRs | Local deployments expose it on localhost |
| T10 | Denial of service: flood of expensive requests | 2 | Rate, token and concurrency limits per key, retry-storm throttling, agent caps, body size cap, WAF on AWS | Upstream provider rate limits still apply |
| T11 | Denial of service: Redis outage disables enforcement | 2 | Fail closed for hard budgets (503); boot guard forbids fail-open on AWS | Availability loss during the outage, by design |
| T12 | Elevation: viewer performs admin actions | 4 | Role checks in the API on every route; sessions die on role change | None known |
| T13 | Elevation: CSRF against a signed-in admin | 4 | `X-TokenShield-CSRF` required for cookie mutations, CORS allowlist, SameSite=Lax | None known |
| T14 | Repudiation: an admin denies changing a budget | 5 | Audit row with actor, IP and details written in the same transaction as the change | Audit rows are visible to admins and owners only |
| T15 | Prompt injection aimed at the downstream application | 6 | Optional heuristic rule (alert or reject) | Heuristics miss novel phrasings; this is defence in depth, not a guarantee |
| T16 | Supply chain: compromised dependency | all | Locked dependencies (`uv.lock`, `pnpm-lock.yaml`), pip-audit, pnpm audit, CodeQL and gitleaks in the opt-in security workflow | Zero-day in a dependency |

## Out of scope

A compromised host or AWS account, leaked deployment secrets, and resource exhaustion of a
deployment you operate yourself. See [SECURITY.md](../../SECURITY.md).
