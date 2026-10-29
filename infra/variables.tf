variable "project_name" {
  type        = string
  description = "Prefix for names of all resources in this project."
  default     = "successfulsuccess"
}

variable "region" {
  type        = string
  description = "AWS region for resources."
  default     = "us-east-1"
}

variable "app_urls" {
  type        = list(string)
  description = "Callback and logout URLs for Cognito authentication."
  default     = ["http://localhost:3000/", "https://d126ea50d9uj6h.cloudfront.net/"]
}

variable "google_client_id" {
  type        = string
  description = "OAuth client ID of Google Cloud Web application client."
  default     = ""
}

variable "google_client_secret" {
  type        = string
  description = "OAuth client secret of Google Cloud Web application client."
  default     = ""
  sensitive   = true
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where Aurora and builder Lambda run."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnets for builder Lambda."
}

variable "route_table_ids" {
  type        = list(string)
  description = "Route table IDs to associate with S3 Gateway VPC endpoint."
}

variable "function_security_group_id" {
  type        = string
  description = "Security group ID for builder Lambda to reach Aurora."
}

variable "database_url" {
  type        = string
  description = "Async PostgreSQL database connection URL for report builder Lambda."
  sensitive   = true
}

variable "image_uri" {
  type        = string
  description = "Container image URI for backend, report builder, and agenda parser Lambdas."
}

variable "architecture" {
  type        = string
  description = "Target Lambda architecture."
  default     = "arm64"
}

variable "app_timezone" {
  type        = string
  description = "Application timezone for schedule and timestamps."
  default     = "Europe/Kyiv"
}

variable "sender_email" {
  type        = string
  description = "Verified sender email in Amazon SES."
}

variable "recipient_email" {
  type        = string
  description = "Verified recipient email in Amazon SES."
}

variable "schedule_expression" {
  type        = string
  description = "EventBridge schedule expression for weekly report."
  default     = "cron(0 7 ? * MON *)"
}

variable "parser_model" {
  type        = string
  description = "Bedrock Claude model ID for agenda parser."
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "cors_origins" {
  type        = list(string)
  description = "Allowed origins for agenda parser CORS."
  default     = ["https://d126ea50d9uj6h.cloudfront.net"]
}
