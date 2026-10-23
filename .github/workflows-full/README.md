# Full CI pipeline (opt-in)

These workflows are the complete quality pipeline for Euron Open TokenShield. They are kept
here, outside `.github/workflows/`, so they do **not** run on the upstream repository.
Only the fast [`checks`](../workflows/checks.yml) workflow (lint, typecheck, unit tests,
web build) runs there.

| Workflow | What it runs |
| --- | --- |
| [`ci.yml`](ci.yml) | Sanitization scan, OpenAPI drift, API integration tests on Postgres 16 (pgvector) and Redis 7 with an 85% coverage floor |
| [`security.yml`](security.yml) | gitleaks over full history, CodeQL (Python and TypeScript), pip-audit, pnpm audit |
| [`terraform.yml`](terraform.yml) | `terraform fmt` and `validate` for every environment, tflint, checkov |
| [`docker.yml`](docker.yml) | Multi-arch image builds for the api and web |
| [`e2e.yml`](e2e.yml) | The full stack on the local AWS emulator: the integration suite under every key and storage backend, the Playwright browser tests and the Puppeteer QA sweep |

To enable them in your fork, move them into `.github/workflows/`:

```bash
git mv .github/workflows-full/*.yml .github/workflows/
```

Every gate is also runnable locally:
`make lint typecheck test test-integration test-matrix e2e qa tf-validate tf-lint tf-security sanitize`.
