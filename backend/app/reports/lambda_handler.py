"""Lambda handler for the report builder.

Invoked by EventBridge Scheduler or SQS. Generates the weekly report CSV
and writes it to the reports S3 bucket.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from app.reports.weekly import (
    build_weekly_report,
    get_last_completed_iso_week,
    get_report_s3_key,
)

logger = logging.getLogger("report_builder")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
if not logger.handlers:
    handler_stream = logging.StreamHandler()
    handler_stream.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s"))
    logger.addHandler(handler_stream)

s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def detect_trigger(event: dict[str, Any], body: dict[str, Any] | None = None) -> str:
    """Detect whether this invocation came from schedule or manual sqs."""
    # If the payload explicitly tells us the source
    if body and body.get("source"):
        return str(body["source"])
    if event.get("source") in ("schedule", "aws.scheduler", "aws.events"):
        return "schedule"
    if "Records" in event:
        first_record = event["Records"][0]
        if first_record.get("eventSource") == "aws:sqs":
            # Check if SQS message body specifies source
            if body and body.get("source"):
                return str(body["source"])
            return "sqs"
    return str(event.get("source", "sqs"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    bucket = os.environ.get("REPORTS_BUCKET")
    if not bucket:
        raise RuntimeError("REPORTS_BUCKET environment variable is not set")

    body: dict[str, Any] = {}
    if "Records" in event and event["Records"]:
        # SQS record shape
        raw_body = event["Records"][0].get("body", "{}")
        try:
            body = json.loads(raw_body)
        except Exception:
            body = {"raw": raw_body}
    else:
        # Direct invocation shape
        body = event

    trigger = detect_trigger(event, body)
    week = body.get("week")
    if not week:
        week = get_last_completed_iso_week()

    # Required log line for submission
    logger.info(
        'report-builder triggered {"trigger": "%s", "week": "%s"}',
        trigger,
        week,
        extra={"trigger": trigger, "week": week},
    )

    csv_bytes = build_weekly_report(week)
    s3_key = get_report_s3_key(week)

    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=csv_bytes,
        ContentType="text/csv",
    )

    logger.info("Successfully uploaded %s to s3://%s/%s", s3_key, bucket, s3_key)
    return {
        "status": "ok",
        "bucket": bucket,
        "key": s3_key,
        "week": week,
        "trigger": trigger,
    }
