# Deploy to AWS

The Terraform in `infra/terraform` provisions a complete production deployment. The
maintainers develop and test against the local emulator (see
[ADR-0005](../architecture/adr/0005-local-aws-emulation.md)); the AWS environments are kept
valid (`terraform validate`, tflint, checkov) on every change, and this guide describes how
to apply them in your own account.

## What gets created

| Module | Resources |
| --- | --- |
| `network` | VPC across two or three availability zones, public and private subnets, NAT, flow logs |
| `database` | RDS PostgreSQL 16 (encrypted, private, automated backups); TokenShield enables `vector` in its first migration |
| `cache` | ElastiCache Valkey replication group with TLS, an auth token and `noeviction` |
| `storage` | Private, TLS-only exports bucket with KMS encryption and 30-day expiry |
| `kms` | Customer-managed key with rotation |
| `secrets` | Session secret, API key pepper and connection strings in Secrets Manager |
| `ecr` | Repositories for the api and web images |
| `service` | ECS Fargate cluster; api, worker and web services behind one ALB (with WAF); a migrate task definition for one-off commands |
| `observability` | CloudWatch log groups, a dashboard and alarms (load balancer 5xx, API latency p95, database CPU, storage and connections, cache, budget rejections) |

The ALB sends `/v1/*`, `/api/*`, `/healthz` and `/readyz` to the api, and everything else to
the dashboard. `/metrics` is served only to `metrics_allowed_cidrs`.

## Steps

```bash
cd infra/terraform/envs/aws-dev        # or aws-prod
cp terraform.tfvars.example terraform.tfvars      # set name_prefix, hostname, certificate, zone
cp backend.tf.example backend.tf                   # recommended: S3 state with locking
terraform init

# 1. Registries first, so there is somewhere to push images.
terraform apply -target=module.ecr

# 2. Build and push both images with the tag set in terraform.tfvars (image_tag).
aws ecr get-login-password | docker login --username AWS --password-stdin <registry>
docker build -f ../../../../infra/docker/api.Dockerfile -t <api repo>:0.1.0 ../../../../apps/api
docker build -f ../../../../infra/docker/web.Dockerfile -t <web repo>:0.1.0 ../../../../apps/web
docker push <api repo>:0.1.0 && docker push <web repo>:0.1.0

# 3. Everything else.
terraform apply

# 4. Migrate, then create the first owner (one-off tasks, parameters in `terraform output run_task`).
aws ecs run-task --cluster <cluster> --task-definition <family> --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=[...],securityGroups=[...]}'
aws ecs run-task ... --overrides '{"containerOverrides":[{"name":"migrate",
  "command":["create-owner","--email","you@example.com"],
  "environment":[{"name":"TOKENSHIELD_OWNER_PASSWORD","value":"<strong password>"}]}]}'
```

Then open `https://<hostname>`, sign in, add your real providers and model prices on the
Models page, create projects and keys, and set budgets.

## Notes

- State contains generated secrets (database password, cache auth token, signing secrets):
  keep the state bucket private, versioned and encrypted.
- `aws-prod` differs from `aws-dev` in resilience and retention: three availability zones
  with a NAT gateway each (dev: two zones, one NAT), VPC interface endpoints, Multi-AZ RDS
  with more storage, a 30-day KMS deletion window (dev: 7) and a year of flow logs (dev: 14 days).
- Never run `seed-demo` against a real deployment (it refuses in production).
- For a cheaper trial, use [local against AWS](local-with-aws.md): local containers with a
  real KMS key and bucket.
