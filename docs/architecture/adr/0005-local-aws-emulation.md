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

**Bad / caveats**
- Emulators prove API compatibility, not IAM. Least-privilege mistakes show up only on real
  AWS, which is what `aws-dev` is for.
- Floci does not persist the KMS rotation period, so a second `terraform plan` shows one
  harmless in-place update.

## Alternatives considered

- **Real AWS for development.** Cost and friction for every contributor.
- **LocalStack.** Similar role; Floci matches the sibling Euron projects and is MIT.
