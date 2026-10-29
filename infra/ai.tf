# =========================================================================
# Agenda Parser IAM Role
# =========================================================================
resource "aws_iam_role" "agenda_parser" {
  name = "${var.project_name}-agenda-parser-role"

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

resource "aws_iam_role_policy_attachment" "agenda_parser_basic" {
  role       = aws_iam_role.agenda_parser.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "agenda_parser_bedrock" {
  name = "BedrockInferenceAccess"
  role = aws_iam_role.agenda_parser.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:GetFoundationModelAvailability",
        "bedrock-mantle:CreateInference"
      ]
      Resource = "*"
    }]
  })
}

# =========================================================================
# Agenda Parser CloudWatch Log Group
# =========================================================================
resource "aws_cloudwatch_log_group" "agenda_parser" {
  name              = "/aws/lambda/${var.project_name}-agenda-parser"
  retention_in_days = 7
}

# =========================================================================
# Agenda Parser Lambda Function (Outside VPC, No NAT required)
# =========================================================================
resource "aws_lambda_function" "agenda_parser" {
  function_name = "${var.project_name}-agenda-parser"
  description   = "Parses raw meeting notes with Amazon Bedrock Claude into structured JSON."
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = [var.architecture]
  role          = aws_iam_role.agenda_parser.arn
  memory_size   = 512
  timeout       = 30

  image_config {
    command = ["app.ai.agenda_lambda.handler"]
  }

  environment {
    variables = {
      COGNITO_REGION       = var.region
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.client.id
      PARSER_MODEL         = var.parser_model
      APP_TIMEZONE         = var.app_timezone
      LOG_LEVEL            = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.agenda_parser]
}

# =========================================================================
# Lambda Function URL (Public HTTPS endpoint, verified via Cognito in app)
# =========================================================================
resource "aws_lambda_function_url" "agenda_parser" {
  function_name      = aws_lambda_function.agenda_parser.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = var.cors_origins
    allow_methods = ["POST"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 300
  }
}

resource "aws_lambda_permission" "agenda_url_public" {
  statement_id           = "FunctionUrlPermission"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.agenda_parser.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
