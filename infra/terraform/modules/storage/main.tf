# One private bucket for usage report exports (CSV). The worker writes each export
# with SSE-KMS; the dashboard hands the admin a short-lived presigned GET. Exports are
# regenerable snapshots of data that lives in Postgres, so they expire on a fixed
# schedule instead of being versioned and kept.
resource "aws_s3_bucket" "exports" {
  #checkov:skip=CKV_AWS_144:Cross-region replication is pointless for regenerable, expiring exports.
  #checkov:skip=CKV_AWS_18:Access logging targets a separate log bucket an operator chooses; CloudTrail data events cover object access (docs/guides/operations.md).
  #checkov:skip=CKV2_AWS_62:No consumer for S3 event notifications.
  #checkov:skip=CKV_AWS_21:Exports are regenerable from Postgres and expire after expiration_days; versioning would only keep expired copies.
  bucket        = "${var.name_prefix}-exports"
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "exports" {
  bucket                  = aws_s3_bucket.exports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "exports" {
  bucket = aws_s3_bucket.exports.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "exports" {
  bucket = aws_s3_bucket.exports.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "exports" {
  bucket = aws_s3_bucket.exports.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # Exports carry usage attribution (projects, keys, end-user ids): keep them only as
  # long as an admin plausibly needs to re-download one.
  rule {
    id     = "expire-exports"
    status = "Enabled"
    filter {}
    expiration {
      days = var.expiration_days
    }
  }
}

# Only needed when a browser fetches objects with JavaScript; a presigned download link
# opened as a navigation needs none, so the default is no CORS at all.
resource "aws_s3_bucket_cors_configuration" "exports" {
  count  = length(var.cors_origins) > 0 ? 1 : 0
  bucket = aws_s3_bucket.exports.id
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.cors_origins
    allowed_headers = ["*"]
    expose_headers  = ["Content-Disposition", "Content-Length", "ETag"]
    max_age_seconds = 3600
  }
}

data "aws_iam_policy_document" "exports" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.exports.arn, "${aws_s3_bucket.exports.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "exports" {
  count      = var.enforce_tls ? 1 : 0
  bucket     = aws_s3_bucket.exports.id
  policy     = data.aws_iam_policy_document.exports.json
  depends_on = [aws_s3_bucket_public_access_block.exports]
}
