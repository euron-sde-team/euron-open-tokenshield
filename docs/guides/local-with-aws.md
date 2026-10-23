# Local containers against real AWS

`make up-aws` runs the same containers as `make up`, but against a real KMS key and S3
bucket instead of the emulator. Postgres and Redis stay local. Use it to check IAM and KMS
behaviour that an emulator cannot prove.

```bash
cd infra/terraform/envs/aws-dev && terraform apply -target=module.kms -target=module.storage
cp deploy/compose/.env.aws.example deploy/compose/.env.aws   # fill EXPORTS_BUCKET and KMS_KEY_ID from terraform output
make up-aws
```

Credentials come from your AWS CLI profile (`AWS_PROFILE`), mounted read-only into the
containers; no static keys are written anywhere. The overlay sets `TOKENSHIELD_CLOUD=aws`,
`KEY_MODE=kms` and `STORAGE=s3`, and the API refuses an `AWS_ENDPOINT_URL` override in this
mode.
