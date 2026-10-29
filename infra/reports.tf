# =========================================================================
# S3 Gateway VPC Endpoint
# =========================================================================
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.route_table_ids
}

# =========================================================================
# S3 Bucket for Weekly Reports
# =========================================================================
resource "aws_s3_bucket" "reports" {
  bucket = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket = aws_s3_bucket.reports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "DeleteAfter90Days"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
  }
}

# =========================================================================
# SQS Queues & Dead Letter Queue
# =========================================================================
resource "aws_sqs_queue" "reports_dlq" {
  name                      = "${var.project_name}-report-requests-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "reports" {
  name                       = "${var.project_name}-report-requests"
  visibility_timeout_seconds = 360

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.reports_dlq.arn
    maxReceiveCount     = 3
  })
}

# =========================================================================
# EventBridge Scheduler
# =========================================================================
resource "aws_iam_role" "schedule" {
  name = "${var.project_name}-reports-ScheduleRole-TppDMGfwMwSL"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "schedule" {
  name = "SendToReportQueue"
  role = aws_iam_role.schedule.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.reports.arn
    }]
  })
}

resource "aws_scheduler_schedule" "weekly_report" {
  name                         = "${var.project_name}-weekly-report-schedule"
  description                  = "Triggers weekly report calculation every Monday morning."
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.app_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sqs_queue.reports.arn
    role_arn = aws_iam_role.schedule.arn
    input    = jsonencode({ week = null, source = "schedule" })
  }
}

# =========================================================================
# Report Builder Lambda Function (In VPC)
# =========================================================================
resource "aws_iam_role" "builder" {
  name = "${var.project_name}-reports-BuilderFunctionRole-3pNRIXCsJjml"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "builder_vpc" {
  role       = aws_iam_role.builder.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "builder" {
  name = "ReportBuilderPermissions"
  role = aws_iam_role.builder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "arn:aws:s3:::${var.project_name}-reports-${data.aws_caller_identity.current.account_id}/reports/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.reports.arn
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "builder" {
  name              = "/aws/lambda/${var.project_name}-report-builder"
  retention_in_days = 7
}

resource "aws_lambda_function" "builder" {
  function_name = "${var.project_name}-report-builder"
  description   = "Generates the weekly CSV report and writes it to S3."
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = [var.architecture]
  role          = aws_iam_role.builder.arn
  memory_size   = 512
  timeout       = 60

  image_config {
    command = ["app.reports.lambda_handler.handler"]
  }

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.function_security_group_id]
  }

  environment {
    variables = {
      DATABASE_URL   = var.database_url
      APP_TIMEZONE   = var.app_timezone
      REPORTS_BUCKET = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}"
      LOG_LEVEL      = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.builder]
}

resource "aws_lambda_event_source_mapping" "builder" {
  event_source_arn = aws_sqs_queue.reports.arn
  function_name    = aws_lambda_function.builder.arn
  batch_size       = 1
  enabled          = true
}

# =========================================================================
# Report Mailer Lambda Function (Outside VPC) & Notification
# =========================================================================
resource "aws_iam_role" "mailer" {
  name = "${var.project_name}-reports-MailerFunctionRole-Fg2DwY71CXCU"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "mailer_basic" {
  role       = aws_iam_role.mailer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "mailer" {
  name = "ReportMailerPermissions"
  role = aws_iam_role.mailer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "arn:aws:s3:::${var.project_name}-reports-${data.aws_caller_identity.current.account_id}/reports/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "mailer" {
  name              = "/aws/lambda/${var.project_name}-report-mailer"
  retention_in_days = 7
}

data "archive_file" "mailer_zip" {
  type        = "zip"
  source_file = "${path.module}/mailer_lambda.py"
  output_path = "${path.module}/mailer_lambda.zip"
}

resource "aws_lambda_function" "mailer" {
  function_name    = "${var.project_name}-report-mailer"
  description      = "Receives S3 ObjectCreated events and sends report CSV via Amazon SES."
  runtime          = "python3.12"
  handler          = "mailer_lambda.handler"
  filename         = data.archive_file.mailer_zip.output_path
  source_code_hash = data.archive_file.mailer_zip.output_base64sha256
  role             = aws_iam_role.mailer.arn
  memory_size      = 256
  timeout          = 30
  architectures    = [var.architecture]

  environment {
    variables = {
      SENDER_EMAIL    = var.sender_email
      RECIPIENT_EMAIL = var.recipient_email
      LOG_LEVEL       = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.mailer]
}

resource "aws_lambda_permission" "s3_mailer" {
  statement_id  = "AllowS3InvokeMailer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.mailer.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.reports.arn
}

resource "aws_s3_bucket_notification" "reports" {
  bucket = aws_s3_bucket.reports.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.mailer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.s3_mailer]
}
