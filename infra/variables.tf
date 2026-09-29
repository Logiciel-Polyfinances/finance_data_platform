variable "project_name" {
  description = "Short name used to prefix all resources (fdp = finance data platform)"
  type        = string
  default     = "fdp"
}

variable "aws_region" {
  description = "Region for the whole stack (same as the Supabase project)"
  type        = string
  default     = "ca-central-1"
}

variable "aws_account_id" {
  description = "Polyfinances AWS account ID; used in ARNs and as a suffix to make S3 bucket names globally unique"
  type        = string
  default     = "437848352148"
}

variable "image_tag" {
  description = "Tag of the Lambda container image in ECR to deploy (CI passes the git commit SHA). No default on purpose: never deploy an unknown image."
  type        = string
}

variable "ssm_prefix" {
  description = "SSM Parameter Store path prefix holding this project's secrets"
  type        = string
  default     = "/finance-data-platform"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for every Lambda log group (short on purpose: log storage is the main recurring cost)"
  type        = number
  default     = 14
}

variable "schedule_timezone" {
  description = "Timezone the EventBridge Scheduler cron expressions are evaluated in (the former Airflow DAGs' timezone)"
  type        = string
  default     = "America/Montreal"
}

variable "schedules_enabled" {
  description = "Master switch for every EventBridge schedule (false = keep the infra, pause all scheduled runs)"
  type        = bool
  default     = true
}

variable "cors_origins" {
  description = "Comma-separated CORS allowed origins for the API (CORS is handled by FastAPI, not API Gateway)"
  type        = string
  default     = "*"
}

# No Redis in AWS: API Gateway throttling replaces the per-key limiter (which
# fails open without REDIS_URL). HTTP APIs have no usage plans/API keys, so
# these are stage/route-wide limits (token bucket, requests per second).
variable "api_throttling_rate_limit" {
  description = "Steady-state requests/second allowed across the whole API"
  type        = number
  default     = 20
}

variable "api_throttling_burst_limit" {
  description = "Burst capacity across the whole API"
  type        = number
  default     = 50
}

variable "register_throttling_rate_limit" {
  description = "Requests/second for POST /v1/instruments and .../refresh, each (start backfills; register hits Yahoo synchronously) -- replaces RATE_LIMIT_WRITE_PER_MINUTE"
  type        = number
  default     = 1
}

variable "register_throttling_burst_limit" {
  description = "Burst capacity for POST /v1/instruments and .../refresh, each"
  type        = number
  default     = 5
}
