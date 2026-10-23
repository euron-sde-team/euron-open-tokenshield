# ADR-0005: A local AWS emulator, provisioned by the same Terraform as production

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

TokenShield uses S3 (report exports, presigned downloads), KMS (sealing provider
credentials with an encryption context) and Secrets Manager. Asking every contributor or
evaluator for an AWS account before they can see the gateway work is a steep on-ramp, and
mocking each SDK call would test the mocks, not the system.

## Decision

Run **[Floci](https://github.com/floci-io/floci)**, an MIT-licensed local AWS emulator, as
a Compose service. Point the unmodified AWS SDK at it with `AWS_ENDPOINT_URL`. A one-shot
container applies `infra/terraform/envs/local-floci`, which uses the same `storage`, `kms`
and `secrets` modules as `aws-dev` and `aws-prod`, before any application container starts.
Postgres and Redis, which Floci does not back, run as plain containers locally and map to
RDS and ElastiCache in the AWS environments.

## Consequences

**Good**
- Clone to a working gateway with only Docker: `make up && make demo`.
- Application code has no emulator branches: everything is configuration
  (`AWS_ENDPOINT_URL`, `S3_FORCE_PATH_STYLE`, `S3_PUBLIC_ENDPOINT`).
- The Terraform runs on every local start, and the integration suite runs under every key
  and storage backend against it (`make test-matrix`).
- The full production environment is exercised too: `make tf-aws-on-floci` plans, applies,
  re-plans and destroys `aws-dev` (148 resources: VPC, RDS, ElastiCache, ECS, ALB, WAF, KMS,
  S3, Secrets Manager, ECR, CloudWatch) against a throwaway Floci. Its first run caught a
  plan-time bug that `terraform validate` cannot see (alarm `for_each` keys derived from an
  apply-time attribute).

**Bad / caveats**
- Emulators prove API compatibility, not IAM. Least-privilege mistakes show up only on real
  AWS, which is what `aws-dev` is for.
- Floci does not persist every attribute: the KMS rotation period, ElastiCache maintenance
  window, transit encryption mode, log delivery and security groups, RDS storage type and
  parameter group values, and an alarm's extended statistic. A re-plan therefore shows a few
  in-place updates against the emulator, never additions or replacements; real AWS stores
  them all.
- Floci deletes ECR repositories only with a backing registry, which needs the Docker socket.
  The apply-and-destroy check leaves ECR to the throwaway emulator rather than hand the
  emulator control of the Docker daemon.

## Alternatives considered

- **Real AWS for development.** Cost and friction for every contributor.
- **LocalStack.** Similar role; Floci matches the sibling Euron projects and is MIT.
