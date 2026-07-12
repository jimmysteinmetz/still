"""Your Day calendar adapter against mocked HTTP — no network, no OAuth in tests."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from still.almanac import calendar as cal

TZ = ZoneInfo("America/New_York")
MONDAY = datetime(2026, 7, 6, 8, 0, tzinfo=TZ)  # a weekday
SATURDAY = datetime(2026, 7, 4, 8, 0, tzinfo=TZ)  # a weekend


def client_for(payload: dict[str, Any], status: int = 200) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload))
    )


def _fetch(client: httpx.Client, *, today: datetime = MONDAY, **kw: Any) -> cal.YourDay | None:
    return cal.fetch("tok", client, today=today, tz=TZ, **kw)


def _with_attendee(event: dict[str, Any]) -> dict[str, Any]:
    """Attach a real, non-declined other attendee — a "real" meeting for tests
    that aren't specifically exercising the other-attendee filter itself."""
    return {
        **event,
        "attendees": [
            {"self": True, "responseStatus": "accepted"},
            {"email": "colleague@example.com", "responseStatus": "accepted"},
        ],
    }


def test_extracts_first_last_and_count() -> None:
    payload = {
        "items": [
            _with_attendee(
                {"start": {"dateTime": "2026-07-06T09:30:00-04:00"}, "summary": "Standup"}
            ),
            _with_attendee({"start": {"dateTime": "2026-07-06T11:00:00-04:00"}, "summary": "1:1"}),
            _with_attendee(
                {"start": {"dateTime": "2026-07-06T16:00:00-04:00"}, "summary": "Review"}
            ),
        ]
    }
    day = _fetch(client_for(payload))
    assert day is not None
    assert day.meeting_count == 3
    assert day.first_time == "9:30 AM"
    assert day.first_title == "Standup"
    assert day.last_time == "4:00 PM"


def test_all_day_events_excluded() -> None:
    payload = {
        "items": [
            {"start": {"date": "2026-07-06"}, "summary": "Company holiday"},
            _with_attendee({"start": {"dateTime": "2026-07-06T10:00:00-04:00"}, "summary": "Sync"}),
        ]
    }
    day = _fetch(client_for(payload))
    assert day is not None
    assert day.meeting_count == 1
    assert day.first_title == "Sync"


def test_declined_events_excluded() -> None:
    payload = {
        "items": [
            {
                "start": {"dateTime": "2026-07-06T08:00:00-04:00"},
                "summary": "Optional sync",
                "attendees": [
                    {"self": True, "responseStatus": "declined"},
                    {"email": "colleague@example.com", "responseStatus": "accepted"},
                ],
            },
            _with_attendee(
                {"start": {"dateTime": "2026-07-06T09:30:00-04:00"}, "summary": "Standup"}
            ),
        ]
    }
    day = _fetch(client_for(payload))
    assert day is not None
    assert day.meeting_count == 1
    assert day.first_time == "9:30 AM"  # the declined 8:00 is dropped


def test_solo_block_excluded() -> None:
    payload = {
        "items": [
            # No attendees key at all — a focus-time/solo block.
            {"start": {"dateTime": "2026-07-06T08:00:00-04:00"}, "summary": "Focus time"},
            # Only attendee is yourself — still solo for this purpose.
            {
                "start": {"dateTime": "2026-07-06T08:30:00-04:00"},
                "summary": "Prep",
                "attendees": [{"self": True, "responseStatus": "accepted"}],
            },
            _with_attendee(
                {"start": {"dateTime": "2026-07-06T09:30:00-04:00"}, "summary": "Standup"}
            ),
        ]
    }
    day = _fetch(client_for(payload))
    assert day is not None
    assert day.meeting_count == 1
    assert day.first_time == "9:30 AM"
    assert day.first_title == "Standup"


def test_all_other_attendees_declined_excluded() -> None:
    payload = {
        "items": [
            {
                "start": {"dateTime": "2026-07-06T08:00:00-04:00"},
                "summary": "Dead meeting",
                "attendees": [
                    {"self": True, "responseStatus": "accepted"},
                    {"responseStatus": "declined"},
                ],
            },
            {
                "start": {"dateTime": "2026-07-06T09:30:00-04:00"},
                "summary": "Standup",
                "attendees": [
                    {"self": True, "responseStatus": "accepted"},
                    {"responseStatus": "accepted"},
                ],
            },
        ]
    }
    day = _fetch(client_for(payload))
    assert day is not None
    assert day.meeting_count == 1
    assert day.first_time == "9:30 AM"
    assert day.first_title == "Standup"


def test_other_attendee_not_yet_responded_counts() -> None:
    payload = {
        "items": [
            {
                "start": {"dateTime": "2026-07-06T09:30:00-04:00"},
                "summary": "Standup",
                "attendees": [
                    {"self": True, "responseStatus": "accepted"},
                    {"responseStatus": "needsAction"},
                ],
            },
        ]
    }
    day = _fetch(client_for(payload))
    assert day is not None
    assert day.meeting_count == 1
    assert day.first_title == "Standup"


def test_no_meetings_returns_zero_not_none() -> None:
    day = _fetch(client_for({"items": []}))
    assert day is not None
    assert day.meeting_count == 0
    assert day.first_time is None
    assert day.first_title is None


def test_weekend_short_circuits() -> None:
    # No HTTP call should be needed; a raising transport proves fetch returns early.
    def boom(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("must not hit the network on a weekend")

    client = httpx.Client(transport=httpx.MockTransport(boom))
    assert _fetch(client, today=SATURDAY, weekdays_only=True) is None


def test_weekend_included_when_not_weekdays_only() -> None:
    payload = {
        "items": [
            _with_attendee(
                {"start": {"dateTime": "2026-07-04T12:00:00-04:00"}, "summary": "Brunch"}
            )
        ]
    }
    day = _fetch(client_for(payload), today=SATURDAY, weekdays_only=False)
    assert day is not None
    assert day.meeting_count == 1


def test_http_error_returns_none() -> None:
    assert _fetch(client_for({}, status=500)) is None


def test_calendar_id_is_url_encoded_in_path() -> None:
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)  # encoded form; .path would decode %40 back to @
        return httpx.Response(200, json={"items": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    _fetch(client, calendar_id="me@work.com")
    assert "me%40work.com" in seen["url"]
