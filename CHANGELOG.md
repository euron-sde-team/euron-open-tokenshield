# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-23

First public release: TokenShield Core.

### Added

- OpenAI-compatible gateway: `POST /v1/chat/completions` (streaming and non-streaming),
  `POST /v1/embeddings`, `GET /v1/models`, authenticated by scoped gateway keys.
- Provider adapters for any OpenAI-compatible API (OpenAI, Ollama, vLLM, LM Studio, Groq)
  and the native Anthropic Messages API, with provider keys sealed by KMS.
- Token tracking: pre-call estimates with tiktoken, provider-reported usage after the call,
  cached input tokens priced separately, versioned price catalog, unpriced models flagged.
- Hard and soft budgets by organisation, team, project, API key, end user and model, over
  daily, weekly, monthly or lifetime windows, enforced by atomic Redis reservations.
- RPM, TPM and concurrency limits per key.
- Exact-match response cache with project and user scopes, request coalescing, and an
  optional pgvector semantic cache.
- Waste rules: prompt size, output allowance, restricted models, prompt injection
  heuristics, retry storms and agent task caps (calls, cost, repeated tool calls, deadline).
- Uncertain outcomes on upstream timeouts, held and reconciled, never recorded as free.
- Idempotency keys, an append-only usage ledger and audit log.
- Dashboard: overview, request log, budgets, policies, projects, keys, models and pricing,
  cache, agent tasks, reports (CSV export to S3), playground, users, audit and settings.
- Terraform for AWS (VPC, RDS, ElastiCache, S3, KMS, Secrets Manager, ECR, ECS Fargate,
  ALB, WAF, CloudWatch) and a local stack on Floci provisioned by the same modules.
