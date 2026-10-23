# tokenshield (API, gateway and worker)

The Python package behind Euron TokenShield: the OpenAI-compatible gateway (`/v1`), the
dashboard API (`/api/v1`), the background worker, and a deterministic mock LLM provider
used by the demo and the test suites.

```bash
uv sync
uv run tokenshield --help          # serve, worker, migrate, openapi, create-owner, seed-demo
uv run pytest tests/unit           # no database, no network
make -C ../.. test-integration     # real Postgres and Redis
```

Layout, conventions and the request pipeline: [CONTRIBUTING.md](../../CONTRIBUTING.md) and
the [low-level design](../../docs/architecture/LLD.md).
