variable "endpoint" {
  description = "Emulator endpoint. http://floci:4566 inside compose, http://localhost:4166 from the host."
  type        = string
  default     = "http://localhost:4166"
}

variable "name_prefix" {
  description = "Must match EXPORTS_BUCKET (<name_prefix>-exports) and KMS_KEY_ID (alias/<name_prefix>) in deploy/compose/compose.floci.yaml."
  type        = string
  default     = "tokenshield-local"
}

variable "cors_origins" {
  description = "Dashboard origins allowed to fetch exports with JavaScript."
  type        = list(string)
  default     = ["http://localhost:4110", "http://127.0.0.1:4110"]
}
