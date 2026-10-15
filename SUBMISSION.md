# Lab 5: A weekly report, built by events — Submission

**Author:** Viktoriia Tesliuk  
**Email:** vikatesluk058@gmail.com / tesliuk.pn@ucu.edu.ua  
**Repository:** [SuccessfulSuccess_ViktoriaTesliuk](https://github.com/ViktoriiaTesliuk/SuccessfulSuccess_ViktoriaTesliuk)

---

## 1. Commit Link
A link to the commit that adds the report (report generation code, CloudFormation template, and both Lambda handlers):

👉 **https://github.com/ViktoriiaTesliuk/SuccessfulSuccess_ViktoriaTesliuk/commit/9913b7782baf37ab2884ee3b4b3af2e6bd08d6df**

*(Short hash: `9913b77`)*

---

## 2. Screenshot of the Email
*(Attached separately as requested: screenshot of the email delivered by Amazon SES to the inbox with the weekly report CSV file attached).*

---

## 3. S3 Recursive Listing Output
Output of `aws s3 ls s3://<your-reports-bucket>/reports/ --recursive`, showing at least two reports (one built by the schedule and one built on demand with `make report-now`):

```bash
aws s3 ls s3://successfulsuccess-reports-094209472391/reports/ --recursive
```

**Output:**
```text
2026-10-15 16:31:06        523 reports/2026-W40.csv
2026-10-15 16:31:55        415 reports/2026-W41.csv
```

* `reports/2026-W40.csv`: generated on demand via `make report-now WEEK=2026-W40`.
* `reports/2026-W41.csv`: generated automatically by the EventBridge Scheduler schedule trigger.

---

## 4. Three CloudWatch Log Lines (One for each trigger)
Each line demonstrates which event started the respective function:

### 1. Schedule Trigger (`trigger=schedule`)
From `/aws/lambda/successfulsuccess-report-builder`:
```text
[INFO] 2026-10-15 16:31:12,062 - report-builder triggered {"trigger": "schedule", "week": "2026-W41"}
```

### 2. SQS Message Trigger (`trigger=sqs`)
From `/aws/lambda/successfulsuccess-report-builder`:
```text
[INFO] 2026-10-15 16:31:05,334 - report-builder triggered {"trigger": "sqs", "week": "2026-W40"}
```

### 3. S3 Upload Trigger (`trigger=s3`)
From `/aws/lambda/successfulsuccess-report-mailer`:
```text
[INFO] 2026-10-15 16:31:06,335 - report-mailer triggered {"trigger": "s3"}
```

---

## 5. Answers to Part 3, Step 7 Questions

### Question 1:
> **The mailer got the same `ObjectCreated` event twice, and the person got two identical emails. Where would you store "this report was already sent", and what would the key be?**

**Answer:**  
We would store this state in **Amazon DynamoDB** (or a dedicated table in PostgreSQL / Redis).  
* **Key:** The unique S3 report key (for example: `reports/2026-W40.csv` or `partition_key = "2026-W40"`).  
* Before sending the email, the mailer performs an atomic conditional write (`attribute_not_exists(report_key)`). If the record already exists, the write fails with a condition check violation, and the mailer skips sending the duplicate email.

---

### Question 2:
> **The builder in the VPC could not reach SES. List three ways to fix that, with their monthly cost: a NAT gateway, a VPC Interface endpoint for SES, and the split you built. Which would you choose with ten more emails a week? With a million?**

**Answer:**  
1. **AWS NAT Gateway:** ~$32/month per Availability Zone (~$0.045/hour) + $0.045/GB data processing fees.
2. **VPC Interface Endpoint (PrivateLink) for SES:** ~$7.20/month per AZ (~$0.01/hour) + $0.01/GB data processing fees.
3. **The Two-Function Split (Built in this lab):** **$0/month base cost** (The S3 Gateway VPC Endpoint is free; Lambda and SES are billed purely per request and covered by the free tier).

* **With 10 emails a week:** Choose the **Two-Function Split**. Paying $7–$32/month for negligible weekly volume is wasteful; the decoupled split has $0 base cost.
* **With 1,000,000 emails a week:** Choose the **VPC Interface Endpoint for SES** (costs ~$7.20/month base, which is far cheaper than a $32+ NAT Gateway, while allowing direct in-VPC SES communication without S3 event decoupling overhead).

---

### Question 3:
> **You could send a presigned S3 link instead of an attachment. A presigned URL signed with a Lambda role's temporary credentials stops working when those credentials expire, often within hours. How would you send a link that works for a week?**

**Answer:**  
Because temporary STS credentials from a Lambda execution role expire within a few hours (maximum 12 hours), any presigned URL generated with them cannot exceed that lifetime. To generate a link that remains valid for 7 days:
1. **CloudFront Signed URLs (Best Practice):** Distribute reports via Amazon CloudFront backed by the private S3 bucket and issue CloudFront signed URLs. They are signed with a CloudFront public/private key pair (Key Group) independent of IAM credential expiry, allowing an arbitrary expiration date (e.g., 7 days or more).
2. **Permanent IAM User Credentials:** Use permanent IAM User credentials (retrieved securely from AWS Secrets Manager) instead of temporary STS tokens to sign the S3 presigned URL up to the 7-day SigV4 maximum limit.

---

### Bonus Note (Sending the same week twice):
> **Send the same week twice. How many emails do you get? Write down why.**

**Answer:**  
You receive **two emails**. While the S3 file storage is idempotent (writing `reports/2026-W40.csv` twice overwrites the same file in place), Amazon S3 emits a new `s3:ObjectCreated:Put` event for every upload/overwrite. Since the mailer Lambda is triggered by every S3 event and does not yet maintain deduplication state, it dispatches an email for each event received.
