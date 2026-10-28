"""Unit tests for weekly meetings report generation."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Meeting, Participant, User
from app.reports.weekly import (
    format_diff,
    generate_weekly_report_csv,
    get_last_completed_iso_week,
    get_previous_iso_week,
    get_report_s3_key,
    parse_iso_week,
)


def test_parse_iso_week():
    start_cur, end_cur, start_prev, end_prev, prev_week = parse_iso_week("2026-W40")
    assert prev_week == "2026-W39"
    assert start_cur.tzinfo == settings.tz
    assert start_cur.year == 2026
    assert start_cur.month == 9
    assert start_cur.day == 28
    assert start_cur.hour == 0
    assert end_cur == start_cur + timedelta(days=7)
    assert start_prev == start_cur - timedelta(days=7)
    assert end_prev == start_cur


def test_parse_iso_week_invalid():
    with pytest.raises(ValueError, match="Invalid ISO week format"):
        parse_iso_week("invalid-week")

    with pytest.raises(ValueError, match="Invalid ISO week format"):
        parse_iso_week("2026-40")

    with pytest.raises(ValueError, match="Invalid ISO week number"):
        parse_iso_week("2026-W60")


def test_get_previous_iso_week():
    assert get_previous_iso_week("2026-W40") == "2026-W39"
    assert get_previous_iso_week("2026-W02") == "2026-W01"


def test_get_last_completed_iso_week():
    dt = datetime(2026, 10, 12, 8, 0, tzinfo=settings.tz)
    assert get_last_completed_iso_week(dt) == "2026-W41"


def test_get_report_s3_key():
    assert get_report_s3_key("2026-W40") == "reports/2026-W40.csv"


def test_format_diff():
    assert format_diff(10, 5, is_int=True) == "+5"
    assert format_diff(5, 10, is_int=True) == "-5"
    assert format_diff(5, 5, is_int=True) == "0"
    assert format_diff(2.5, 1.0, is_int=False) == "+1.50"
    assert format_diff(1.0, 2.5, is_int=False) == "-1.50"
    assert format_diff(1.0, 1.0, is_int=False) == "0.00"


@pytest.mark.asyncio
async def test_generate_weekly_report_empty(session: AsyncSession):
    csv_text = await generate_weekly_report_csv(session, "2026-W40")
    assert "# Weekly Meetings Report,2026-W40" in csv_text
    assert "Number of Meetings,0,0,0" in csv_text
    assert "Total Duration (hours),0.00,0.00,0.00" in csv_text
    assert "No meetings scheduled for this week" in csv_text


@pytest.mark.asyncio
async def test_generate_weekly_report_with_data(session: AsyncSession):
    # Setup test users
    user1 = User(
        id="sub-alice-123",
        email="alice@example.com",
        name="Alice Wonderland",
        auth_provider="cognito",
    )
    user2 = User(
        id="sub-bob-456",
        email="bob@example.com",
        name="Bob Builder",
        auth_provider="cognito",
    )
    session.add_all([user1, user2])
    await session.commit()

    # 2026-W40 starts on Monday 2026-09-28
    # 2026-W39 starts on Monday 2026-09-21
    tz = settings.tz

    # Prev week meeting: 1 meeting, 1 hour
    prev_m = Meeting(
        owner_id=user1.id,
        name="Prev Week Retro",
        starts_at=datetime(2026, 9, 22, 10, 0, tzinfo=tz),
        ends_at=datetime(2026, 9, 22, 11, 0, tzinfo=tz),
    )

    # Current week meetings:
    # Meeting 1: Alice, 2 hours, 2 participants
    cur_m1 = Meeting(
        owner_id=user1.id,
        name="Sprint Planning",
        starts_at=datetime(2026, 9, 28, 10, 0, tzinfo=tz),
        ends_at=datetime(2026, 9, 28, 12, 0, tzinfo=tz),
        participants=[
            Participant(name="Alice", position=0),
            Participant(name="Bob", position=1),
        ],
    )
    # Meeting 2: Bob, 3 hours, 3 participants (longest)
    cur_m2 = Meeting(
        owner_id=user2.id,
        name="Architecture Deep Dive",
        starts_at=datetime(2026, 9, 29, 14, 0, tzinfo=tz),
        ends_at=datetime(2026, 9, 29, 17, 0, tzinfo=tz),
        participants=[
            Participant(name="Bob", position=0),
            Participant(name="Charlie", position=1),
            Participant(name="David", position=2),
        ],
    )

    session.add_all([prev_m, cur_m1, cur_m2])
    await session.commit()

    csv_text = await generate_weekly_report_csv(session, "2026-W40")

    # Assertions
    assert "Number of Meetings,2,1,+1" in csv_text
    assert "Total Duration (hours),5.00,1.00,+4.00" in csv_text
    assert "Alice Wonderland,alice@example.com,1,2.00" in csv_text
    assert "Bob Builder,bob@example.com,1,3.00" in csv_text
    assert "Architecture Deep Dive,Bob Builder" in csv_text
    assert "Sprint Planning,Alice Wonderland" in csv_text


def test_builder_lambda_handler_direct(monkeypatch):
    from app.reports import lambda_handler

    uploaded = {}

    def mock_put_object(**kwargs):
        uploaded.update(kwargs)
        return {}

    monkeypatch.setenv("REPORTS_BUCKET", "test-reports-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setattr(lambda_handler.s3_client, "put_object", mock_put_object)
    monkeypatch.setattr(
        lambda_handler,
        "build_weekly_report",
        lambda week: b"# Weekly Meetings Report,2026-W40\n",
    )

    event = {"week": "2026-W40", "source": "schedule"}
    result = lambda_handler.handler(event, None)

    assert result["status"] == "ok"
    assert result["bucket"] == "test-reports-bucket"
    assert result["key"] == "reports/2026-W40.csv"
    assert result["trigger"] == "schedule"
    assert uploaded["Bucket"] == "test-reports-bucket"
    assert uploaded["Key"] == "reports/2026-W40.csv"
    assert b"# Weekly Meetings Report" in uploaded["Body"]


def test_builder_lambda_handler_sqs(monkeypatch):
    import json

    from app.reports import lambda_handler

    uploaded = {}

    def mock_put_object(**kwargs):
        uploaded.update(kwargs)
        return {}

    monkeypatch.setenv("REPORTS_BUCKET", "test-reports-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setattr(lambda_handler.s3_client, "put_object", mock_put_object)
    monkeypatch.setattr(
        lambda_handler,
        "build_weekly_report",
        lambda week: b"# Weekly Meetings Report,2026-W39\n",
    )

    event = {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "body": json.dumps({"week": "2026-W39", "source": "sqs"}),
            }
        ]
    }
    result = lambda_handler.handler(event, None)

    assert result["status"] == "ok"
    assert result["key"] == "reports/2026-W39.csv"
    assert result["trigger"] == "sqs"
    assert uploaded["Key"] == "reports/2026-W39.csv"


def test_mailer_lambda_handler(monkeypatch):
    import io

    from app.reports import mailer

    sent_emails = []

    def mock_get_object(**kwargs):
        return {"Body": io.BytesIO(b"Col1,Col2\nVal1,Val2\n")}

    def mock_send_email(**kwargs):
        sent_emails.append(kwargs)
        return {"MessageId": "msg-123"}

    monkeypatch.setenv("SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("RECIPIENT_EMAIL", "recipient@example.com")
    monkeypatch.setattr(mailer.s3_client, "get_object", mock_get_object)
    monkeypatch.setattr(mailer.ses_client, "send_email", mock_send_email)

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "reports%2F2026-W40.csv"},
                }
            }
        ]
    }
    result = mailer.handler(event, None)

    assert result["status"] == "ok"
    assert len(sent_emails) == 1
    assert sent_emails[0]["FromEmailAddress"] == "sender@example.com"
    assert sent_emails[0]["Destination"]["ToAddresses"] == ["recipient@example.com"]
    raw_bytes = sent_emails[0]["Content"]["Raw"]["Data"]
    assert b"Weekly Meetings Report: 2026-W40.csv" in raw_bytes
    assert b'filename="2026-W40.csv"' in raw_bytes
