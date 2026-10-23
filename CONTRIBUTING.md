# Contributing

Thanks for helping improve Euron Open TokenShield. This guide covers the workflow, the bar a
change has to clear, and the conventions the codebase follows.

## Ground rules

- **Open an issue first** for anything larger than a bug fix or a docs tweak, so we can
  agree on the approach before you invest time.
- **One concern per pull request.** A refactor and a feature are two PRs.
- **Security issues go through private reporting**, never a public issue. See
  [SECURITY.md](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE).

## Development setup

Requirements: Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 and
pnpm 9 (`corepack enable`).

```bash
make up          # Postgres, Redis, Floci (provisioned by Terraform), mock LLM, api, worker, web
make demo        # demo organisation, 60 days of history, live traffic
make test        # unit tests (API and web)
```

[docs/guides/quickstart-local.md](docs/guides/quickstart-local.md) walks through the local
stack in detail.

## Before you open a pull request

Each of these must pass:

```bash
make lint typecheck test
make test-integration                  # the API against real Postgres and Redis
make e2e                               # when you touched a dashboard flow or infrastructure
make tf-validate tf-lint tf-security   # when you touched infra/terraform
make openapi                           # when you changed an endpoint (a test checks drift)
make sanitize                          # no credentials, account ids, resource ids or dashes
```

## Conventions

**Package by domain.** `apps/api/src/tokenshield/<domain>/` owns its `router.py` (HTTP
only), `schemas.py` (the public contract), `service.py` (rules), `models.py` and, where it
has queries of its own, `repository.py`. Dependencies point inward: router, service, data.
A domain calls another domain's service, never its tables. The gateway's read model
(`gateway/catalog.py`) is the one deliberate exception, documented in the LLD.

**Every provider call is reserved first.** A new code path that reaches a provider must go
through `GatewayService` so it is attributed, policed, reserved and accounted. The
integration suite asserts zero upstream calls for refused requests; keep it that way.

**Money is integer nano-dollars.** Never use floats for amounts inside the API. Convert at
the edges with `core/money.py` and the `Usd` schema type.

**The hot path does not wait on Postgres.** Gateway configuration is read from the
in-process `ConfigCache`, and usage is written through the Redis Stream. Any admin write
that changes gateway behaviour calls `config_cache.invalidate()`.

**External systems sit behind a Protocol.** Providers (`ProviderAdapter`), key sealing
(`KeySealer`) and storage (`ObjectStorage`). Adding a provider means adding an adapter and
one line in `providers/adapters/registry.py`.

**Configuration is validated.** A new setting goes in `core/config.py`, is documented in
[docs/guides/configuration.md](docs/guides/configuration.md) in the same PR, and
security-relevant ones are enforced by `Settings.guard()` at boot.

**Database changes are new migrations.** Add an Alembic revision under
`apps/api/src/tokenshield/migrations/versions/`. Never edit an applied one. Indexes for
every new filter the API exposes belong in the same revision.

**Comments explain why.** The code says what it does. Comments are for the constraint, the
incident, or the trade-off that made it this way.

**Style.** ruff and mypy `--strict` for Python; ESLint and TypeScript strict for the web.
No em dashes or en dashes anywhere (the sanitization check enforces it).

## Commit messages

Imperative mood with an optional scope: `budgets: rebuild counters from the ledger`,
`web: show the reservation table in the request drawer`. Explain the why in the body when
it is not obvious.

## Architecture decisions

Significant decisions are recorded in [docs/architecture/adr/](docs/architecture/adr/).
If your change reverses or extends one, add a new ADR rather than editing the old one.
