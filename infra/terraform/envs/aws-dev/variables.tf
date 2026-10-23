variable "region" {
  description = "AWS region."
  type        = string
}

variable "environment" {
  description = "Environment tag."
  type        = string
  default     = "dev"
}

variable "extra_tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}

variable "name_prefix" {
  description = "Prefix for every resource name (at most 24 characters); the exports bucket name derives from it, so make it globally unique (e.g. \"acme-tokenshield-dev\")."
  type        = string
}

variable "hostname" {
  description = "Public host name of the deployment, e.g. tokenshield-dev.example.com."
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate in the same region covering hostname."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the hostname alias record. Null: create the CNAME yourself (load_balancer_dns_name output)."
  type        = string
  default     = null
}

variable "image_tag" {
  description = "Image tag to deploy (the git commit or a release)."
  type        = string
}

variable "alarm_email" {
  description = "Alarm notification address."
  type        = string
  default     = null
}

variable "api_extra_environment" {
  description = "Extra api/worker environment (e.g. BUDGET_FAILURE_MODE, STORE_CONTENT). Never secrets."
  type        = map(string)
  default     = {}
}

variable "semantic_cache" {
  description = "Enable the pgvector semantic cache (SEMANTIC_CACHE)."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.small"
}

variable "cache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "metrics_allowed_cidrs" {
  description = "Source CIDRs allowed to scrape /metrics through the load balancer."
  type        = list(string)
  default     = []
}

variable "budget_rejection_threshold" {
  description = "Budget rejections per 5 minutes that raise an alarm. Null: no alarm."
  type        = number
  default     = null
}
