# Security

TokenShield holds the keys to an organisation's LLM providers and decides who may spend
them. This document covers how it protects those keys, who can do what, and what an
operator must configure. The threat analysis is in [threat-model.md](threat-model.md).

## Gateway keys

- Format `tsk_<prefix>_<secret>`: a 12-hex-character prefix (the lookup key) and a
  32-byte URL-safe random secret.
- Stored as **HMAC-SHA256(secret, API_KEY_PEPPER)**. A leaked database alone cannot be
  turned into working keys; the pepper lives in Secrets Manager, not in the database.
  Comparison is constant time.
- The full key is shown once, at creation. Listing endpoints return `tsk_<prefix>_****`.
- Keys carry their own RPM, TPM and concurrency limits and an optional expiry. Revocation
  takes effect cluster-wide within about a second (config version stamp, see
  [caching.md](caching.md)).

## Provider credentials

- Written once through the API, never returned. Responses expose only `has_key` and a hint
  (the last four characters).
- Sealed before storage. With `KEY_MODE=kms` (the AWS and Floci default), the credential is
  encrypted by AWS KMS with the encryption context `tokenshield:record = provider:<id>`, so
  a ciphertext copied onto another provider row fails to decrypt. With `KEY_MODE=local`,
  AES-256-GCM with a key derived from `LOCAL_MASTER_KEY` and the same context as associated
  data.
- Decrypted values are cached in process memory per ciphertext digest, so KMS is called
  only when a credential changes.

## Dashboard authentication

- Passwords hashed with argon2id. Policy: at least 10 characters with upper and lower case
  letters and a digit.
- Unknown emails take the same time as wrong passwords (a dummy hash is verified).
- Five consecutive failures lock an account for 15 minutes; sign-in is also throttled to
  20 attempts per minute per IP.
- Sessions are HS256 JWTs (`SESSION_SECRET`, audience `tokenshield-dashboard`,
  `SESSION_TTL_HOURS`), carried in an `httpOnly`, `SameSite=Lax` cookie (`Secure` when
  `COOKIE_SECURE=true`) or as a bearer token for API clients.
- Every session carries the user's `session_version`. Changing a password, changing a
  role or disabling an account bumps it, which ends all existing sessions immediately.
- **CSRF:** cookie-authenticated mutations must send `X-TokenShield-CSRF: 1`. Browsers
  cannot add a custom header to a cross-site request without a CORS preflight, which the
  allowlist refuses. Bearer-authenticated requests need no such header, because browsers
  never attach Authorization headers cross-site.

## Authorisation

| Role | Can |
| --- | --- |
| viewer | Read everything except users and the audit log |
| admin | Everything a viewer can, plus manage projects, keys, providers, models, prices, budgets, policies, cache, exports and the playground; list users; read the audit log |
| owner | Everything, plus invite users, change roles and disable accounts |

Roles are enforced by the API (the dashboard only hides controls). Guards keep at least one
active owner, prevent changing your own role, and let only owners manage owners.

## Data handling

- Prompts and responses are **not stored** by default. Cached bodies live in Redis for
  their TTL only. `STORE_CONTENT=true` adds short prompt excerpts to usage events and cache
  entries for debugging; leave it off where prompts are sensitive.
- `usage_events`, `reconciliation_events` and `audit_log` are append-only (database
  triggers). Every dashboard mutation writes an audit row in the same transaction.
- JSON logs redact `authorization`, `api_key`, `password`, `secret`, `token` and
  `x-api-key` fields, whatever a caller puts in them.
- CSV exports neutralise spreadsheet formula injection in caller-supplied fields
  (`end_user`, `task_id`).

## HTTP hardening

- Security headers on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Opener-Policy: same-origin`, a restrictive `Permissions-Policy`.
- CORS allowlist from `CORS_ORIGINS`; credentials allowed only for those origins.
- Request bodies are capped at 8 MB on the gateway. Errors never include stack traces or
  internal detail; unhandled exceptions return a generic 500 and are logged with the
  request id.
- On AWS, the ALB serves `/metrics` only to `metrics_allowed_cidrs` (it exposes spend), and
  a WAF with managed rules sits in front; rules that inspect request bodies run in count
  mode, because prompts routinely contain code.

## Production boot guards

With `ENVIRONMENT=production`, the API refuses to start unless:

- `SESSION_SECRET` and `API_KEY_PEPPER` are random values of at least 32 characters, are
  not the development defaults, and differ from each other,
- `LOCAL_MASTER_KEY` is set to a strong value when `KEY_MODE=local`,
- `AWS_ENDPOINT_URL` is unset when `TOKENSHIELD_CLOUD=aws`,
- `BUDGET_FAILURE_MODE` is not `open` when `TOKENSHIELD_CLOUD=aws`.

The demo seed refuses to run in production.

## Operator checklist

- [ ] Generate `SESSION_SECRET` and `API_KEY_PEPPER` with a CSPRNG (the Terraform `secrets`
      module does) and keep them in Secrets Manager.
- [ ] Use `KEY_MODE=kms` with a dedicated key; restrict `kms:Decrypt` to the API and worker
      task roles (the `service` module does).
- [ ] Set `COOKIE_SECURE=true` and serve the dashboard over HTTPS only.
- [ ] Set `CORS_ORIGINS` to the dashboard's exact origin.
- [ ] Keep `BUDGET_FAILURE_MODE=closed`.
- [ ] Keep `STORE_CONTENT=false` unless you need prompt excerpts, and set a retention
      policy if you enable it.
- [ ] Run Redis with AOF persistence and `noeviction` (budget counters must never be
      silently evicted), with TLS and an auth token (the `cache` module does).
- [ ] Restrict `/metrics` to your monitoring network.
- [ ] Create the first owner with `tokenshield create-owner`, then invite other users with
      the least role they need.
- [ ] Rotate provider keys from the Models page; rotate gateway keys by creating a new key,
      deploying it, then revoking the old one.
- [ ] Never run `make demo` or `seed-demo` against a real deployment.
