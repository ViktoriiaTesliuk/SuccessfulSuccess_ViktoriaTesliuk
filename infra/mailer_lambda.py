import json
import logging
import os
import urllib.parse
from email.message import EmailMessage
import boto3

logger = logging.getLogger("report_mailer")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s"))
    logger.addHandler(h)

s3_client = boto3.client("s3")
ses_client = boto3.client("sesv2")


def handler(event, context):
    logger.info('report-mailer triggered {"trigger": "s3"}', extra={"trigger": "s3"})

    records = event.get("Records", [])
    if not records:
        return {"status": "no_records"}

    sender = os.environ.get("SENDER_EMAIL")
    recipients_raw = os.environ.get("RECIPIENT_EMAIL", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    for record in records:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        raw_key = s3_info.get("object", {}).get("key")
        if not bucket or not raw_key:
            continue

        key = urllib.parse.unquote_plus(raw_key)
        filename = os.path.basename(key)

        try:
            logger.info("Downloading s3://%s/%s", bucket, key)
            obj = s3_client.get_object(Bucket=bucket, Key=key)
            csv_bytes = obj["Body"].read()

            msg = EmailMessage()
            msg["Subject"] = f"Weekly Meetings Report: {filename}"
            msg["From"] = sender
            msg["To"] = ", ".join(recipients)
            msg.set_content(
                f"Hello,\n\nPlease find attached the weekly meetings report: {filename}.\n\nBest regards,\nSpry Reporting System"
            )

            msg.add_attachment(
                csv_bytes,
                maintype="text",
                subtype="csv",
                filename=filename,
            )

            logger.info("Sending email via Amazon SES to %s", recipients)
            ses_client.send_email(
                FromEmailAddress=sender,
                Destination={"ToAddresses": recipients},
                Content={"Raw": {"Data": msg.as_bytes()}},
            )
            logger.info("Report email sent successfully for %s", filename)

        except Exception as exc:
            logger.error("Failed to process report %s: %s", key, exc, exc_info=True)
            raise

    return {"status": "success", "processed": len(records)}
