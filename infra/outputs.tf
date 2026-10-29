# =========================================================================
# Auth Outputs (Cognito)
# =========================================================================
output "UserPoolId" {
  value       = aws_cognito_user_pool.main.id
  description = "Cognito User Pool ID"
}

output "UserPoolClientId" {
  value       = aws_cognito_user_pool_client.client.id
  description = "Cognito User Pool Web Client ID"
}

output "Issuer" {
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  description = "Token issuer URL"
}

output "HostedDomain" {
  value       = "${aws_cognito_user_pool_domain.domain.domain}.auth.${var.region}.amazoncognito.com"
  description = "Cognito hosted UI OAuth domain"
}

output "GoogleRedirectUri" {
  value       = "https://${aws_cognito_user_pool_domain.domain.domain}.auth.${var.region}.amazoncognito.com/oauth2/idpresponse"
  description = "Authorized redirect URI for Google OAuth client"
}

output "GoogleEnabled" {
  value       = var.google_client_id != "" ? "true" : "false"
  description = "Whether Google OAuth sign-in is enabled"
}

# =========================================================================
# Reports Outputs
# =========================================================================
output "ReportsBucketName" {
  value       = aws_s3_bucket.reports.id
  description = "S3 bucket storing weekly meeting reports"
}

output "ReportsBucketArn" {
  value       = aws_s3_bucket.reports.arn
  description = "ARN of reports S3 bucket"
}

output "QueueUrl" {
  value       = aws_sqs_queue.reports.url
  description = "URL of SQS report requests queue"
}

output "QueueArn" {
  value       = aws_sqs_queue.reports.arn
  description = "ARN of SQS report requests queue"
}

output "DlqUrl" {
  value       = aws_sqs_queue.reports_dlq.url
  description = "URL of SQS dead-letter queue"
}

output "DlqArn" {
  value       = aws_sqs_queue.reports_dlq.arn
  description = "ARN of SQS dead-letter queue"
}

output "BuilderFunctionName" {
  value       = aws_lambda_function.builder.function_name
  description = "Name of the report builder Lambda function"
}

output "MailerFunctionName" {
  value       = aws_lambda_function.mailer.function_name
  description = "Name of the report mailer Lambda function"
}

output "ScheduleName" {
  value       = aws_scheduler_schedule.weekly_report.name
  description = "Name of the EventBridge Scheduler schedule"
}

# =========================================================================
# Agenda Parser (AI) Outputs
# =========================================================================
output "AgendaParserFunctionName" {
  value       = aws_lambda_function.agenda_parser.function_name
  description = "Name of the agenda parser Lambda function"
}

output "AgendaParserUrl" {
  value       = aws_lambda_function_url.agenda_parser.function_url
  description = "Base URL of the agenda parser (Lambda Function URL)"
}

output "AgendaLogGroupName" {
  value       = aws_cloudwatch_log_group.agenda_parser.name
  description = "CloudWatch log group name for agenda parser"
}
