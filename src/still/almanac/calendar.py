"""Your Day module — Google Calendar (spec §4A, §6).

One `events.list` call for today's window (`singleEvents=true` so recurring
meetings are expanded server-side, `orderBy=startTime` so the list arrives
sorted). The earliest *timed* event with at least one other non-declined
attendee is the "first meeting" (solo/focus-time blocks and events every
other invitee declined don't count); we also carry the last start time and a
total count. Weekdays only per config — the weekend edition deliberately has
no "first meeting" (spec §4.0).

Auth is OAuth: `still calendar auth` runs the one-time installed-app consent and
stores an authorized-user token; `load_credentials` reloads it and refreshes
silently. The actual API call rides on httpx (same idiom as the other almanac
modules), so `fetch` is unit-testable with a MockTransport and never touches the
network in tests. Fails gracefully — no token / a dead API / a weekend all return
None and the masthead line simply omits.
"""

import logging
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Read-only, least privilege. Changing this invalidates existing tokens (re-auth).
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
API_ROOT = "https://www.googleapis.com/calendar/v3/calendars"


class YourDay(BaseModel):
    """Render-ready masthead summary of today's calendar."""

    meeting_count: int  # timed events today (all-day events excluded)
    first_time: str | None  # "9:30 AM"; None when the day is clear
    first_title: str | None  # earliest meeting's title
    last_time: str | None  # latest meeting's start time


def load_credentials(token_path: Path) -> Credentials | None:
    """Load the stored authorized-user token, refreshing it if expired.

    Returns None (logged, never raised) when the token is missing, malformed, or
    unrefreshable — the caller then hides Your Day rather than breaking the build.
    A successful refresh is persisted so the next run starts from a fresh token.
    """
    if not token_path.exists():
        return None
    try:
        creds: Credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
            str(token_path), SCOPES
        )
    except (ValueError, OSError) as e:
        logger.warning("your day: unreadable token %s: %s", token_path, e)
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())  # type: ignore[no-untyped-call]
        except GoogleAuthError as e:
            logger.warning("your day: token refresh failed: %s", e)
            return None
        # Cache the refreshed token — best-effort. Only the short-lived access token
        # changed (the refresh token is unchanged), so a read-only filesystem — e.g. a
        # Secret Manager mount on Cloud Run — is safe to skip: the next run just refreshes
        # again from the same durable refresh token.
        try:
            token_path.write_text(creds.to_json())  # type: ignore[no-untyped-call]
        except OSError as e:
            logger.warning("your day: couldn't cache refreshed token (%s); continuing", e)
        return creds
    logger.warning("your day: token invalid; re-run 'still calendar auth'")
    return None


def fetch(
    access_token: str,
    client: httpx.Client,
    *,
    today: datetime,
    tz: tzinfo,
    weekdays_only: bool = True,
    calendar_id: str = "primary",
) -> YourDay | None:
    """Summarize today's calendar. None on a weekend (when weekdays_only) or error."""
    if weekdays_only and today.weekday() >= 5:  # Sat/Sun
        return None
    start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    try:
        resp = client.get(
            f"{API_ROOT}/{quote(calendar_id, safe='')}/events",
            params={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": "50",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        events = resp.json().get("items", [])
    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning("your day unavailable: %s", e)
        return None

    # Keep only timed events you haven't declined, with at least one other real
    # attendee — an all-day banner, a meeting you said no to, a solo/focus-time
    # block, or one where every other invitee declined isn't "your first meeting".
    # orderBy=startTime keeps them sorted.
    timed = [
        e
        for e in events
        if "dateTime" in (e.get("start") or {}) and not _declined(e) and _has_other_attendee(e)
    ]
    if not timed:
        return YourDay(meeting_count=0, first_time=None, first_title=None, last_time=None)
    return YourDay(
        meeting_count=len(timed),
        first_time=_fmt_time(timed[0]["start"]["dateTime"], tz),
        first_title=(timed[0].get("summary") or "Untitled").strip(),
        last_time=_fmt_time(timed[-1]["start"]["dateTime"], tz),
    )


def _declined(event: dict[str, Any]) -> bool:
    return any(
        att.get("self") and att.get("responseStatus") == "declined"
        for att in (event.get("attendees") or [])
    )


def _has_other_attendee(event: dict[str, Any]) -> bool:
    """At least one non-self attendee who hasn't declined.

    Excludes solo/focus-time blocks (no ``attendees`` key at all, or the only
    entry is yourself) and events where every *other* invitee has declined —
    neither is really "a meeting" for the masthead line. "accepted",
    "tentative", and "needsAction" all count as a real other attendee.
    """
    return any(
        not att.get("self") and att.get("responseStatus") != "declined"
        for att in (event.get("attendees") or [])
    )


def _fmt_time(dt_str: str, tz: tzinfo) -> str:
    """RFC3339 start → local "9:30 AM"."""
    return datetime.fromisoformat(dt_str).astimezone(tz).strftime("%-I:%M %p")
