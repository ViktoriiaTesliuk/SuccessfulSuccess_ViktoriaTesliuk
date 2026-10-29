project_name = "successfulsuccess"
region       = "us-east-1"
app_urls = [
  "http://localhost:3000/",
  "https://d126ea50d9uj6h.cloudfront.net/"
]
google_client_id = "1015925038947-68jubrhnjdh7c750ijhmu0lf3khv50md.apps.googleusercontent.com"
app_timezone     = "Europe/Kyiv"

vpc_id = "vpc-0ed76e6f1b5ca904b"
subnet_ids = [
  "subnet-03584bcf7fbd2dfa8",
  "subnet-0ff65436dc53cec2d",
  "subnet-06d228bdffa7b0e26",
  "subnet-06cf3fd370afd8357",
  "subnet-0e866931c62c7200b",
  "subnet-03d82378ebe21cc72"
]
route_table_ids            = ["rtb-0c10aa9b20bce6b9c"]
function_security_group_id = "sg-0f51d01388861760e"
image_uri                  = "094209472391.dkr.ecr.us-east-1.amazonaws.com/successfulsuccess-backend@sha256:23d561418590ed3a552e3c607644b508d4312436fb49cd4c37fb50a12b0c71e7"
architecture               = "arm64"

sender_email        = "vikatesluk058@gmail.com"
recipient_email     = "vikatesluk058@gmail.com"
schedule_expression = "cron(0 7 ? * MON *)"

parser_model = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
cors_origins = ["https://d126ea50d9uj6h.cloudfront.net"]
