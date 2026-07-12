"""Shared helpers for almanac modules."""

from datetime import date, datetime


def parse_date(raw: str | None) -> date | None:
    """Date from the leading YYYY-MM-DD of an API datetime string; None if absent/malformed."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
