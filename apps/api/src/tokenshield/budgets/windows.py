"""Budget periods as UTC calendar windows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

PERIODS = ("daily", "weekly", "monthly", "total")


def window_start(period: str, now: datetime) -> datetime | None:
    now = now.astimezone(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "daily":
        return day
    if period == "weekly":
        return day - timedelta(days=day.weekday())
    if period == "monthly":
        return day.replace(day=1)
    if period == "total":
        return None
    raise ValueError(f"unknown period {period}")


def window_end(period: str, now: datetime) -> datetime | None:
    start = window_start(period, now)
    if start is None:
        return None
    if period == "daily":
        return start + timedelta(days=1)
    if period == "weekly":
        return start + timedelta(days=7)
    # monthly
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)


def window_label(period: str, now: datetime) -> str:
    start = window_start(period, now)
    if start is None:
        return "all"
    return start.strftime("%Y%m%d")


def window_ttl_s(period: str, now: datetime) -> int:
    """Seconds the counter must live: to the end of the window plus a day of grace."""
    end = window_end(period, now)
    if end is None:
        return 0
    return int((end - now.astimezone(UTC)).total_seconds()) + 86400
