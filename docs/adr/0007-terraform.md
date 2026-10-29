# ADR 0007: Migration from CloudFormation to Terraform with HCP Terraform Remote Execution and Zero Data Loss

- **Status:** Accepted
- **Date:** 2026-10-29
- **Context:** Spry / SuccessfulSuccess Meetings Application (Module 7 / Lab 7)

---

## 1. Context and Problem Statement

From Labs 3 through 6, our infrastructure was provisioned using AWS CloudFormation templates:
- `infra/auth.yml`: Amazon Cognito User Pool, Hosted Domain, User Pool Client, and Google Identity Provider.
- `infra/reports.yml`: Private S3 reports bucket, SQS request & dead-letter queues, EventBridge scheduler, VPC gateway endpoint for S3, inline Python mailer Lambda, and containerized builder Lambda.
- `infra/as.yml`: Containerized Claude agenda parser Lambda, IAM Bedrock inference policies, and public Lambda Function URL with CORS.

### Limitations of CloudFormation in Production:
1. **Circular Dependencies:** CloudFormation enforces that S3 bucket event notifications must often be declared within the bucket resource, which creates a circular dependency with the target Lambda permission. In Lab 5, this forced an explicit naming workaround.
2. **State & Drift Visibility:** CloudFormation hides the desired vs. actual resource graph in opaque stack change-sets that do not cleanly isolate multi-tier changes.
3. **Pipeline Coupling:** Applying infrastructure changes locally requires developer laptops to hold long-lived administrator AWS credentials.
4. **Code Duplication & Inline Blobs:** Python Lambda handlers were embedded directly into YAML string literals without syntax highlighting, linting, or modular packaging.

We need to migrate our infrastructure definitions from AWS CloudFormation to **HashiCorp Terraform (HCL)**, managed centrally via **HCP Terraform**, while guaranteeing **zero data loss** (preserving all existing Cognito registered users and S3 reports).

---

## 2. Decisions

### 2.1 Codebase Layout

We organized our Terraform configuration into a single flat module under `infra/`:

| File | Purpose |
|---|---|
| [`infra/versions.tf`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/versions.tf) | Declares required provider versions (`hashicorp/aws` ~> 6.0, `hashicorp/random`, `hashicorp/archive`) and the `cloud` block connecting to HCP Terraform organization `ooad-lab7` and workspace `successfulsuccess-dev`. Configures global `default_tags` (`ManagedBy = "terraform"`, `PROJECT_NAME = var.project_name`). |
| [`infra/variables.tf`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/variables.tf) | Declares typed variables for project identifiers, networking, images, schedules, and secrets. Sensitive variables (`database_url`, `google_client_secret`) are marked `sensitive = true`. |
| [`infra/auth.tf`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/auth.tf) | Translates `infra/auth.yml` into `aws_cognito_user_pool`, `aws_cognito_user_pool_domain`, `aws_cognito_user_pool_client`, and conditional `aws_cognito_identity_provider` for Google OAuth. |
| [`infra/reports.tf`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/reports.tf) | Translates `infra/reports.yml`. Decouples S3 bucket notifications (`aws_s3_bucket_notification`) and Lambda permissions from bucket creation, eliminating the circular dependency. Archives [`infra/mailer_lambda.py`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/mailer_lambda.py) cleanly using `data.archive_file`. |
| [`infra/ai.tf`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/ai.tf) | Translates `infra/as.yml`. Defines the Bedrock Claude agenda parser Lambda, CloudWatch log group, IAM permissions, and public Lambda Function URL with CORS headers. |
| [`infra/outputs.tf`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/outputs.tf) | Exports all infrastructure outputs (`UserPoolId`, `AgendaParserUrl`, `ReportsBucketName`, `QueueUrl`, etc.) consumable by the frontend build, local backend, and Makefile. |
| [`infra/terraform.tfvars`](file:///Users/viktoriia/Desktop/lab2%20ooad/infra/terraform.tfvars) | Environment-specific non-sensitive parameter values for the development deployment. |

### 2.2 State-Backend Choice: HCP Terraform with Remote Execution and AWS OIDC

Rather than using an S3 bucket and DynamoDB table for state storage, we chose **HCP Terraform (formerly Terraform Cloud)** in `remote` execution mode:
- **Centralized Locking and State:** State is stored encrypted at rest and locked automatically during runs, eliminating state corruption from concurrent runs.
- **Short-Lived Dynamic Credentials (OIDC):** By configuring an AWS OpenID Connect Identity Provider (`app.terraform.io`) and an IAM execution role (`arn:aws:iam::094209472391:role/hcp-terraform-ooad-lab7`), HCP Terraform assumes permissions dynamically using short-lived tokens. No long-lived AWS secret access keys exist in the HCP workspace.
- **Speculative Plans on Pull Requests:** Integrating GitHub with HCP Terraform provides automated speculative plans on pull requests, allowing code reviewers to inspect exact infrastructure changes before merging.
- **Auditability:** Complete history of who triggered each plan and apply, with exact commit SHAs.

### 2.3 Safe Zero-Loss Migration Strategy

A naive migration of *"delete the CloudFormation stacks, then run terraform apply"* is catastrophic in production: deleting `successfulsuccess-auth` would destroy the Cognito User Pool and delete every user account registered since Lab 4; deleting `successfulsuccess-reports` would delete the S3 reports bucket and all weekly reports.

We executed a zero-loss three-step migration workflow:

```
[CloudFormation: Retain]           [Detachment]                    [Terraform Adoption]
Add DeletionPolicy: Retain   -->   aws cloudformation delete-stack  -->  imports.tf (import { to, id })
Deploy stacks once more            Stacks deleted, resources stay        terraform plan until 0 destroy
                                                                         terraform apply -> In sync!
```

1. **Retain Policies:** Added `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` to every resource across `auth.yml`, `reports.yml`, and `as.yml`, and redeployed all three stacks.
2. **CloudFormation Detachment:** Deleted the CloudFormation stacks using `aws cloudformation delete-stack`. Because of the `Retain` policies, the stacks dissolved while all physical AWS resources remained live and untouched.
3. **Terraform Import Blocks:** Declared Terraform 1.5+ native `import { to = ... id = ... }` blocks in `infra/imports.tf` mapping every live AWS resource ID to its Terraform address.
4. **Iterative Plan Refinement:** Ran `terraform plan` to compare live attributes against HCL. Omitted creation-only attributes (such as `generate_secret = false` on Cognito Client) that would force replacement (`-/+`), matching existing provider attributes until `Plan: 31 to import, 2 to add, 19 to change, 0 to destroy`.
5. **Apply & Cleanup:** Applied the import into HCP Terraform. Verified post-migration plan showed `No changes. Your infrastructure matches the configuration.` Removed `infra/imports.tf` and deleted the obsolete `.yml` templates.

### 2.4 Re-created Child Resources

As documented in the lab guidelines, ephemeral authorization permissions (`aws_lambda_permission.s3_mailer` and `aws_lambda_permission.agenda_url_public`) were clean-recreated rather than imported. Because CloudFormation assigned nondeterministic statement IDs, deleting the obsolete policy statements and having Terraform provision clean, deterministic statement IDs (`AllowS3InvokeMailer`, `FunctionUrlPermission`) caused zero downtime and ensured clean state.

---

## 3. Alternatives Considered

| Alternative | Rationale for Rejection |
|---|---|
| **S3 + DynamoDB State Backend** | Requires provisioning, securing, and maintaining an S3 bucket and DynamoDB locking table manually. Requires developers or CI runners to maintain long-lived AWS IAM credentials with state bucket permissions, increasing key leakage risk. |
| **Naive "Delete & Re-apply"** | Completely unacceptable for stateful and authentication infrastructure. Deletes all user credentials in Cognito and all customer reports in S3. |
| **Terraform Modules per Sub-system** | Creating nested module directories (`modules/auth`, `modules/reports`) for an infrastructure consisting of ~30 resources introduces unnecessary HCL boilerplate and variable pass-through complexity for a single environment. A flat structure in `infra/` is simpler, more readable, and easier to audit. |

---

## 4. Operational Considerations & Key Architectural Questions

### 4.1 Why Terraform and not CloudFormation, CDK, or OpenTofu for this project?
- **Versus CloudFormation:** CloudFormation is tied strictly to AWS and cannot manage non-AWS resources like the Google Cloud OAuth client, GitHub repository rules, or multi-cloud assets. Furthermore, CloudFormation creates circular dependencies (e.g., S3 bucket notifications and Lambda permissions) and lacks interactive speculative plans (`terraform plan`).
- **Versus AWS CDK:** CDK is a code generator that synthesizes CloudFormation templates under the hood, inheriting all of CloudFormation's deployment-time limitations, slow rollback cycles, and opaque stack states.
- **Versus OpenTofu:** While OpenTofu is an open-source drop-in fork, Terraform was chosen for native, first-class integration with HCP Terraform's managed workspace platform, automated speculative plans, and native OIDC credential exchange without additional management overhead.

### 4.2 Who can change the infrastructure now, and how?
- **No Direct Laptop Applies:** Developers no longer run `terraform apply` with admin AWS keys from local laptops.
- **Pull Request & VCS Workflow:** Any infrastructure modification must be proposed as a branch and GitHub Pull Request.
- **Automated Speculative Plans:** HCP Terraform automatically runs a speculative plan against the PR, posting the exact diff as a commit check for peer review.
- **Automated Apply on Merge:** Only upon merging the PR into `main` does HCP Terraform trigger the remote `apply`, assuming the short-lived AWS IAM OIDC role (`arn:aws:iam::094209472391:role/hcp-terraform-ooad-lab7`).

### 4.3 Where do secrets end up, including the state?
- **Sensitive Variables in HCP Terraform:** Sensitive inputs (`database_url`, `google_client_secret`) are configured directly in the HCP Terraform workspace as sensitive variables. They are never written to `git`, `.env`, or `.tfvars`.
- **State Storage:** The Terraform state file is stored encrypted at rest inside HCP Terraform. While the state file contains raw attribute values required for diffing, access to the state is strictly restricted to authorized workspace members and the HCP execution runner via RBAC.
- **Dynamic AWS Credentials:** No AWS secret access keys exist anywhere; AWS access is granted exclusively through short-lived STS tokens via OpenID Connect (OIDC).

### 4.4 What happens if HCP Terraform is down?
- **No Impact on Running Infrastructure:** The existing AWS resources (Cognito User Pool, Lambdas, S3 bucket, Aurora, SQS) continue to operate normally without interruption. Running workloads do not query HCP Terraform.
- **Break-Glass Emergency Procedure:** If HCP Terraform suffers an extended outage and emergency changes are needed, a privileged administrator can download the latest state snapshot, configure a local backend or temporary S3/DynamoDB backend, authenticate via local AWS CLI credentials, and execute emergency operations directly.

---

## 5. Consequences & Pipeline Integration

- **Makefile Automation:** Stack output queries via CloudFormation were replaced with `$(TF) output -raw <key>`. Deployment commands (`aws-deploy-auth`, `aws-deploy-reports`, `aws-deploy-agenda`) now delegate to `infra-plan` to preview changes locally without applying.
- **Continuous Deployment (Two Roads):** Infrastructure applies are strictly decoupled from application container pushes. Infrastructure updates are reviewed via HCP Terraform PR checks and applied automatically upon merge to `main`. Application code is built and deployed via GitHub Actions workflows.
