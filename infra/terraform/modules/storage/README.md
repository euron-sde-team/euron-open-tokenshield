# `storage` module

One private S3 bucket, `<name_prefix>-exports`, for usage report exports (CSV). The worker writes each object with SSE-KMS; the API returns a short-lived presigned GET for the download.

- Public access blocked, bucket-owner-enforced ownership, TLS-only bucket policy (`aws:SecureTransport`).
- Default encryption SSE-KMS with the CMK (bucket key on), SSE-S3 when no key is given.
- Lifecycle: objects expire after `expiration_days` (30 by default), incomplete multipart uploads abort after a day. Exports are regenerable from Postgres, so the bucket is not versioned.
- Optional CORS (`cors_origins`), only for JavaScript fetches from the dashboard.

Applied in `local-floci` as `tokenshield-local-exports` with `enforce_tls = false` (the emulator speaks plain HTTP) and `force_destroy = true`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The bucket is `<name_prefix>-exports`. | `string` | required |
| `kms_key_arn` | CMK for SSE-KMS. Null falls back to SSE-S3. | `string` | `null` |
| `enforce_tls` | Deny any request not made over TLS. | `bool` | `true` |
| `expiration_days` | Days an export object is kept. | `number` | `30` |
| `cors_origins` | Browser origins allowed to GET objects with JavaScript. Empty = no CORS. | `list(string)` | `[]` |
| `force_destroy` | Allow destroying a non-empty bucket. Never in production. | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `bucket_name` | Exports bucket name (`EXPORTS_BUCKET`). |
| `bucket_arn` | Exports bucket ARN, for IAM policies. |
