# ADR-0001: One deployment serves one organisation

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

TokenShield sits between an organisation's applications and its LLM providers, and it
holds that organisation's provider credentials. The people who install a self-hosted
gateway are platform teams protecting their own spend. They need teams, projects, keys
and budgets inside one organisation, not a hosting business serving unrelated customers.

Multi-organisation isolation is expensive to get right: every table needs a tenant column,
every query a structural scope, every cache key and Redis counter a tenant prefix, and the
test suite an isolation sweep. The sibling Euron Open HRMS carries all of that because it
is a SaaS by design.

## Decision

One deployment serves exactly one organisation. Inside it, attribution and policy work at
five levels: the whole gateway, team, project, API key, and end user (plus per model).
Dashboard users belong to the organisation and have one of three roles: owner, admin,
viewer.

## Consequences

**Good**
- Every gateway path is simpler and faster: no tenant resolution, no tenant prefix on hot
  Redis keys, and a catalog snapshot that is the whole configuration.
- Provider credentials and the KMS key belong to one organisation, which matches how
  security teams want to reason about them.
- Fewer ways to get isolation wrong. The isolation that matters here (one project's or one
  user's cached answers never served to another) is still enforced, by cache partitions
  (see [caching.md](../caching.md)).

**Bad / caveats**
- A provider of TokenShield as a service would run one deployment per customer. The
  Terraform makes that a variable change, but it costs more than a shared database.
- Moving to multi-organisation later means a migration that adds an organisation column
  and a scoped repository layer. The domain packages keep that change contained.

## Alternatives considered

- **Multi-tenant from day one** (HRMS style). Rejected for 0.1.0: cost without a user.
- **Teams as the top-level boundary with hard isolation.** Rejected: teams inside one
  organisation routinely share models, providers and an overall budget.
