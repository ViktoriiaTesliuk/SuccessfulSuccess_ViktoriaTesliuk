"""Weekly meetings report generator.

Pure business logic with no AWS dependencies.
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Meeting, User


def parse_iso_week(week: str) -> tuple[datetime, datetime, datetime, datetime, str]:
    """Parse an ISO week string like '2026-W40'.

    Returns (start_of_week, end_of_week, start_of_prev_week, end_of_prev_week, prev_week_str)
    all timezone-aware in the application's configured timezone.
    """
    match = re.match(r"^(\d{4})-W(\d{1,2})$", week.strip())
    if not match:
        raise ValueError(
            f"Invalid ISO week format '{week}'. Expected format 'YYYY-Www', e.g. '2026-W40'."
        )

    year = int(match.group(1))
    week_num = int(match.group(2))
    if week_num < 1 or week_num > 53:
        raise ValueError(f"Invalid ISO week number {week_num}. Must be between 1 and 53.")

    # Monday of the requested week
    monday_date = datetime.fromisocalendar(year, week_num, 1).date()
    next_monday_date = monday_date + timedelta(days=7)
    prev_monday_date = monday_date - timedelta(days=7)

    tz = settings.tz
    start_of_week = datetime.combine(monday_date, time.min, tzinfo=tz)
    end_of_week = datetime.combine(next_monday_date, time.min, tzinfo=tz)

    start_of_prev_week = datetime.combine(prev_monday_date, time.min, tzinfo=tz)
    end_of_prev_week = start_of_week

    prev_y, prev_w, _ = prev_monday_date.isocalendar()
    prev_week_str = f"{prev_y}-W{prev_w:02d}"

    return start_of_week, end_of_week, start_of_prev_week, end_of_prev_week, prev_week_str


def get_previous_iso_week(week: str) -> str:
    """Return the previous ISO week string given a week string."""
    _, _, _, _, prev_week_str = parse_iso_week(week)
    return prev_week_str


def get_last_completed_iso_week(now: datetime | None = None) -> str:
    """Return the ISO week string of the week that just completed.

    Useful for scheduled runs (e.g. running on Monday morning to report on the previous week).
    """
    if now is None:
        now = datetime.now(settings.tz)
    last_week_date = now - timedelta(days=7)
    y, w, _ = last_week_date.isocalendar()
    return f"{y}-W{w:02d}"


def get_report_s3_key(week: str) -> str:
    """Return the idempotent S3 object key for a given ISO week report."""
    clean_week = week.strip()
    return f"reports/{clean_week}.csv"


def format_diff(curr: float, prev: float, is_int: bool = False) -> str:
    diff = curr - prev
    if is_int:
        diff_val = int(diff)
        return f"+{diff_val}" if diff_val > 0 else str(diff_val)
    if abs(diff) < 1e-6:
        return "0.00"
    return f"+{diff:.2f}" if diff > 0 else f"{diff:.2f}"


async def generate_weekly_report_csv(session: AsyncSession, week: str) -> str:
    """Query the database and return the CSV text for the given ISO week."""
    (
        start_of_week,
        end_of_week,
        start_of_prev_week,
        end_of_prev_week,
        prev_week_str,
    ) = parse_iso_week(week)

    # 1. Fetch current week's meetings
    curr_result = await session.execute(
        select(Meeting)
        .options(selectinload(Meeting.participants))
        .where(Meeting.starts_at >= start_of_week, Meeting.starts_at < end_of_week)
        .order_by(Meeting.starts_at.asc())
    )
    curr_meetings: Sequence[Meeting] = curr_result.scalars().all()

    # 2. Fetch previous week's meetings
    prev_result = await session.execute(
        select(Meeting)
        .options(selectinload(Meeting.participants))
        .where(Meeting.starts_at >= start_of_prev_week, Meeting.starts_at < end_of_prev_week)
    )
    prev_meetings: Sequence[Meeting] = prev_result.scalars().all()

    # 3. Fetch users for organizers
    all_owner_ids = {m.owner_id for m in curr_meetings if m.owner_id}
    users_by_id: dict[str, User] = {}
    if all_owner_ids:
        users_result = await session.execute(select(User).where(User.id.in_(all_owner_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    # Compute aggregates
    curr_count = len(curr_meetings)
    curr_duration_hours = (
        sum((m.ends_at - m.starts_at).total_seconds() for m in curr_meetings) / 3600.0
    )

    prev_count = len(prev_meetings)
    prev_duration_hours = (
        sum((m.ends_at - m.starts_at).total_seconds() for m in prev_meetings) / 3600.0
    )

    count_diff_str = format_diff(curr_count, prev_count, is_int=True)
    duration_diff_str = format_diff(curr_duration_hours, prev_duration_hours, is_int=False)

    # Breakdown per organizer
    organizer_stats: dict[str | None, dict[str, float | int]] = {}
    for m in curr_meetings:
        stats = organizer_stats.setdefault(m.owner_id, {"count": 0, "duration": 0.0})
        stats["count"] += 1
        stats["duration"] += (m.ends_at - m.starts_at).total_seconds() / 3600.0

    # Top 5 longest meetings
    longest_meetings = sorted(
        curr_meetings,
        key=lambda m: (m.ends_at - m.starts_at).total_seconds(),
        reverse=True,
    )[:5]

    output = io.StringIO()
    writer = csv.writer(output)

    # Header / Title
    writer.writerow(["# Weekly Meetings Report", week])
    writer.writerow([])

    # Section 1: Summary & Comparison
    writer.writerow(["Metric", f"This Week ({week})", f"Previous Week ({prev_week_str})", "Change"])
    writer.writerow(["Number of Meetings", str(curr_count), str(prev_count), count_diff_str])
    writer.writerow(
        [
            "Total Duration (hours)",
            f"{curr_duration_hours:.2f}",
            f"{prev_duration_hours:.2f}",
            duration_diff_str,
        ]
    )
    writer.writerow([])

    # Section 2: Breakdown per Organizer
    writer.writerow(["# Breakdown by Organizer"])
    writer.writerow(["Organizer Name", "Email", "Meetings Count", "Total Duration (hours)"])
    if organizer_stats:
        # Sort by total duration descending
        sorted_organizers = sorted(
            organizer_stats.items(),
            key=lambda item: item[1]["duration"],
            reverse=True,
        )
        for owner_id, stats in sorted_organizers:
            user = users_by_id.get(owner_id) if owner_id else None
            user_name = user.name if user and user.name else (owner_id or "Unassigned")
            user_email = user.email if user and user.email else "N/A"
            writer.writerow(
                [
                    user_name,
                    user_email,
                    stats["count"],
                    f"{stats['duration']:.2f}",
                ]
            )
    else:
        writer.writerow(["None", "None", 0, "0.00"])
    writer.writerow([])

    # Section 3: Top 5 Longest Meetings
    writer.writerow(["# Top 5 Longest Meetings"])
    writer.writerow(
        [
            "Rank",
            "Title",
            "Organizer",
            "Start Time",
            "Duration (hours)",
            "Participants Count",
        ]
    )
    if longest_meetings:
        for rank, m in enumerate(longest_meetings, start=1):
            user = users_by_id.get(m.owner_id) if m.owner_id else None
            user_name = user.name if user and user.name else (m.owner_id or "Unassigned")
            dur = (m.ends_at - m.starts_at).total_seconds() / 3600.0
            start_str = m.starts_at.astimezone(settings.tz).strftime("%Y-%m-%d %H:%M %Z")
            participants_count = len(m.participants)
            writer.writerow(
                [
                    rank,
                    m.name,
                    user_name,
                    start_str,
                    f"{dur:.2f}",
                    participants_count,
                ]
            )
    else:
        writer.writerow(["-", "No meetings scheduled for this week", "-", "-", "-", 0])

    return output.getvalue()


async def _run_async(week: str) -> bytes:
    report_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(
        report_engine, expire_on_commit=False, autoflush=False
    )
    try:
        async with session_factory() as session:
            csv_text = await generate_weekly_report_csv(session, week)
            return csv_text.encode("utf-8")
    finally:
        await report_engine.dispose()



def build_weekly_report(week: str) -> bytes:
    """Query the meetings of one ISO week (e.g. '2026-W40') and return the CSV."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run_async(week)).result()
    return asyncio.run(_run_async(week))
