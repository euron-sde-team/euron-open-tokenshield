output "bucket_name" {
  description = "Exports bucket name (EXPORTS_BUCKET)."
  value       = aws_s3_bucket.exports.bucket
}

output "bucket_arn" {
  description = "Exports bucket ARN, for IAM policies."
  value       = aws_s3_bucket.exports.arn
}
