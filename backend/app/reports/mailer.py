"""Lambda handler for the report mailer.

Triggered by S3 ObjectCreated events for reports/*.csv.
Downloads the report from S3 and sends it as an email attachment via Amazon SES.
Runs outside the VPC so it has direct internet access to SES.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from email.message import EmailMessage
from typing import Any

import boto3

logger = logging.getLogger("report_mailer")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
if not logger.handlers:
    handler_stream = logging.StreamHandler()
    handler_stream.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s"))
    logger.addHandler(handler_stream)

s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
ses_client = boto3.client("sesv2", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def send_report_email(
    bucket: str,
    key: str,
    sender: str,
    recipients: list[str],
) -> None:
    """Download the report from S3 and email it via Amazon SES."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    content = response["Body"].read()

    filename = os.path.basename(key)
    msg = EmailMessage()
    msg["Subject"] = f"Weekly Meetings Report: {filename}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        f"Hello,\n\nPlease find attached the weekly meetings report ({filename}).\n\n"
        f"S3 Object: s3://{bucket}/{key}\n"
    )
    msg.add_attachment(
        content,
        maintype="text",
        subtype="csv",
        filename=filename,
    )

    ses_client.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": recipients},
        Content={"Raw": {"Data": msg.as_bytes()}},
    )
    logger.info("Sent %s to %s via SES", filename, recipients)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # Required log line for submission item 4
    logger.info('report-mailer triggered {"trigger": "s3"}', extra={"trigger": "s3"})

    records = event.get("Records", [])
    if not records:
        logger.warning("No records in event")
        return {"status": "no_records"}

    sender = os.environ.get("SENDER_EMAIL")
    recipients_raw = os.environ.get("RECIPIENT_EMAIL", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    if not sender or not recipients:
        raise RuntimeError("SENDER_EMAIL and RECIPIENT_EMAIL environment variables must be set")

    processed = []
    for record in records:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        raw_key = s3_info.get("object", {}).get("key")
        if not bucket or not raw_key:
            continue

        key = urllib.parse.unquote_plus(raw_key)
        logger.info("Processing S3 object s3://%s/%s", bucket, key)
        send_report_email(bucket, key, sender, recipients)
        processed.append(f"s3://{bucket}/{key}")

    return {"status": "ok", "processed": processed}
