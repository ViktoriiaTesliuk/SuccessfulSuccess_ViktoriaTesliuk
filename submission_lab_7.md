# Lab 7 Submission: The Cloud as Code — From CloudFormation to Terraform

**Student:** Viktoriia Tesliuk  
**Course:** Object-Oriented Analysis and Design (OOAD) / Cloud Architecture  
**Repository:** [SuccessfulSuccess_ViktoriaTesliuk](https://github.com/ViktoriiaTesliuk/SuccessfulSuccess_ViktoriaTesliuk)  
**AWS Account ID:** `094209472391` (Region: `us-east-1`)  
**HCP Terraform Organization:** `ooad-lab7`  
**HCP Terraform Workspace:** `successfulsuccess-dev` (Execution Mode: `remote`)  

---

## Deliverable 1: Commit Link Replacing CloudFormation with Terraform HCL

- **Commit Link:** [7ed8085](https://github.com/ViktoriiaTesliuk/SuccessfulSuccess_ViktoriaTesliuk/commit/7ed8085)
- **Summary of Changes:**
  1. **HCL Translation:** Replaced CloudFormation templates (`infra/auth.yml`, `infra/reports.yml`, `infra/as.yml`) with modular Terraform configuration in `infra/`:
     - `infra/versions.tf`: Configured AWS provider (~> 6.0) with global default tags, archive provider, and HCP Terraform `cloud` block.
     - `infra/variables.tf`: Defined parameters with sensitive attributes for secrets.
     - `infra/auth.tf`: Cognito User Pool, Hosted Domain, User Pool Client, Google IdP.
     - `infra/reports.tf`: S3 reports bucket, SQS request & DLQ queues, EventBridge scheduler, VPC gateway endpoint, inline mailer Lambda, and builder Lambda. Circular dependency resolved by decoupling S3 notifications and Lambda permissions.
     - `infra/mailer_lambda.py`: Clean Python extraction packaged via `data.archive_file`.
     - `infra/ai.tf`: Claude Bedrock agenda parser Lambda, Function URL, CORS, and IAM roles.
     - `infra/outputs.tf`: Consolidated outputs for frontend and backend consumption.
     - `infra/terraform.tfvars`: Environment parameters.
  2. **Makefile Modernization:** Switched stack output lookups from CloudFormation to `$(TF) output -raw <key>`. Replaced `aws cloudformation deploy` targets with `infra-plan` (no local `terraform apply`; applies happen via HCP Terraform CI/CD).
  3. **Documentation:** Updated `README.md` and created ADR [`docs/adr/0007-terraform.md`](docs/adr/0007-terraform.md) covering layout, state-backend choice, and the zero-loss adoption strategy.
  4. **Zero Data Loss Guarantee:** Used `DeletionPolicy: Retain` on CloudFormation before stack deletion, followed by Terraform `import` blocks, ensuring no recreation or downtime for the Cognito User Pool or S3 reports bucket.

---

## Deliverable 2: HCP Terraform Workspace Run ("Apply finished" Triggered via GitHub)

- **Workspace:** `https://app.terraform.io/app/ooad-lab7/successfulsuccess-dev`
- **Execution Mode:** `remote` (authenticated dynamically to AWS via OpenID Connect IAM Role `arn:aws:iam::094209472391:role/hcp-terraform-ooad-lab7`)
- **VCS Connection:** Connected to GitHub repository `ViktoriiaTesliuk/SuccessfulSuccess_ViktoriaTesliuk` with working directory `infra`.
- **Screenshot:** *(Attach screenshot showing the run overview with "Apply finished" and the trigger indicating the commit/merge from GitHub, e.g., `Triggered by push/merge`)*

---

## Deliverable 3: Output of `terraform plan` Immediately After Migration

The post-migration `terraform plan` proves that 100% of live resources match the Terraform configuration with zero drift:

```text
Running plan in HCP Terraform. Output will stream here. Pressing Ctrl-C
will stop streaming the logs, but will not stop the plan running remotely.

Preparing the remote plan...

To view this run in a browser, visit:
https://app.terraform.io/app/ooad-lab7/successfulsuccess-dev/runs/run-WBmsupa9ddVkNjgw

Waiting for the plan to start...

Terraform v1.17.1
on linux_amd64

Initializing plugins and modules...
data.archive_file.mailer_zip: Refreshing...
data.archive_file.mailer_zip: Refresh complete after 0s [id=e5068f7ae8dd17abfe67690c6643bb6e2ded0ba3]
data.aws_caller_identity.current: Refreshing...
aws_cloudwatch_log_group.mailer: Refreshing state... [id=/aws/lambda/successfulsuccess-report-mailer]
aws_sqs_queue.reports_dlq: Refreshing state... [id=https://sqs.us-east-1.amazonaws.com/094209472391/successfulsuccess-report-requests-dlq]
aws_iam_role.mailer: Refreshing state... [id=successfulsuccess-reports-MailerFunctionRole-Fg2DwY71CXCU]
aws_cloudwatch_log_group.builder: Refreshing state... [id=/aws/lambda/successfulsuccess-report-builder]
data.aws_region.current: Refreshing...
aws_iam_role.builder: Refreshing state... [id=successfulsuccess-reports-BuilderFunctionRole-3pNRIXCsJjml]
aws_iam_role.schedule: Refreshing state... [id=successfulsuccess-reports-ScheduleRole-TppDMGfwMwSL]
aws_iam_role.agenda_parser: Refreshing state... [id=successfulsuccess-agenda-parser-role]
aws_cognito_user_pool.main: Refreshing state... [id=us-east-1_W2vTYogcK]
data.aws_region.current: Refresh complete after 0s [id=us-east-1]
aws_vpc_endpoint.s3: Refreshing state... [id=vpce-07d04e60ca57b0e7d]
data.aws_caller_identity.current: Refresh complete after 0s [id=094209472391]
aws_cloudwatch_log_group.agenda_parser: Refreshing state... [id=/aws/lambda/successfulsuccess-agenda-parser]
aws_s3_bucket.reports: Refreshing state... [id=successfulsuccess-reports-094209472391]
aws_sqs_queue.reports: Refreshing state... [id=https://sqs.us-east-1.amazonaws.com/094209472391/successfulsuccess-report-requests]
aws_iam_role_policy.builder: Refreshing state... [id=successfulsuccess-reports-BuilderFunctionRole-3pNRIXCsJjml:ReportBuilderPermissions]
aws_iam_role_policy_attachment.builder_vpc: Refreshing state... [id=successfulsuccess-reports-BuilderFunctionRole-3pNRIXCsJjml/arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole]
aws_lambda_function.builder: Refreshing state... [id=successfulsuccess-report-builder]
aws_scheduler_schedule.weekly_report: Refreshing state... [id=default/successfulsuccess-weekly-report-schedule]
aws_iam_role_policy.schedule: Refreshing state... [id=successfulsuccess-reports-ScheduleRole-TppDMGfwMwSL:SendToReportQueue]
aws_iam_role_policy_attachment.agenda_parser_basic: Refreshing state... [id=successfulsuccess-agenda-parser-role/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole]
aws_iam_role_policy.agenda_parser_bedrock: Refreshing state... [id=successfulsuccess-agenda-parser-role:BedrockInferenceAccess]
aws_iam_role_policy_attachment.mailer_basic: Refreshing state... [id=successfulsuccess-reports-MailerFunctionRole-Fg2DwY71CXCU/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole]
aws_lambda_function.mailer: Refreshing state... [id=successfulsuccess-report-mailer]
aws_iam_role_policy.mailer: Refreshing state... [id=successfulsuccess-reports-MailerFunctionRole-Fg2DwY71CXCU:ReportMailerPermissions]
aws_cognito_identity_provider.google[0]: Refreshing state... [id=us-east-1_W2vTYogcK:Google]
aws_cognito_user_pool_domain.domain: Refreshing state... [id=successfulsuccess-094209472391]
aws_s3_bucket_lifecycle_configuration.reports: Refreshing state... [id=successfulsuccess-reports-094209472391]
aws_s3_bucket_public_access_block.reports: Refreshing state... [id=successfulsuccess-reports-094209472391]
aws_cognito_user_pool_client.client: Refreshing state... [id=48s8nsdcvc4fhb1ubfnmuolklc]
aws_lambda_event_source_mapping.builder: Refreshing state... [id=b100ca40-054d-417b-b713-ca4efb5eab0e]
aws_lambda_permission.s3_mailer: Refreshing state... [id=AllowS3InvokeMailer]
aws_lambda_function.agenda_parser: Refreshing state... [id=successfulsuccess-agenda-parser]
aws_s3_bucket_notification.reports: Refreshing state... [id=successfulsuccess-reports-094209472391]
aws_lambda_permission.agenda_url_public: Refreshing state... [id=FunctionUrlPermission]
aws_lambda_function_url.agenda_parser: Refreshing state... [id=successfulsuccess-agenda-parser]

No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration and
found no differences, so no changes are needed.

───────────────────────────────────────────────────────────────────────────────

Note: You didn't use the -out option to save this plan, so Terraform can't
guarantee to take exactly these actions if you run "terraform apply" now.
```
