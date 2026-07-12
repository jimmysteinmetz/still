"""Upcoming Shows — the reader's bands playing the NYC metro (SeatGeek API).

One call per artist: SeatGeek's `/2/events`, geo-fenced to a lat/lon/range and
filtered to upcoming dates, soonest first. We keep the next show whose lineup
actually names the artist (the `q` search can match loosely). A free `client_id`
is required (https://seatgeek.com/account/develop) — without it the card hides,
never blocks a build. Each artist is fetched in isolation so one bad lookup skips
that row, not the card (spec §2 — sources fail gracefully).
"""

import logging
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel

from still.almanac.util import parse_date

logger = logging.getLogger(__name__)

BASE = "https://api.seatgeek.com/2"


class ShowRow(BaseModel):
    """One render-ready Upcoming Shows line."""

    artist: str  # the followed artist (as configured)
    date: date  # for sorting; not rendered directly
    date_token: str  # "Aug 2"
    venue: str  # venue name
    city: str = ""  # venue city, shown when it isn't Manhattan proper


def fetch_shows(
    artists: list[str],
    client: httpx.Client,
    *,
    lat: float,
    lng: float,
    range_mi: int,
    today: date,
    client_id: str | None,
    max_rows: int = 6,
) -> list[ShowRow]:
    """Next upcoming show per artist within range of (lat, lng), soonest first.
    Empty (no key, none in range, all errored) → the card hides."""
    if not client_id:
        return []
    rows: list[ShowRow] = []
    for artist in artists:
        try:
            row = _artist_next_show(artist, client, lat, lng, range_mi, today, client_id)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            logger.warning("shows: %s skipped: %s", artist, e)
            continue
        if row:
            rows.append(row)
    rows.sort(key=lambda r: r.date)
    return rows[:max_rows]


def _artist_next_show(
    artist: str,
    client: httpx.Client,
    lat: float,
    lng: float,
    range_mi: int,
    today: date,
    client_id: str,
) -> ShowRow | None:
    params: dict[str, str | float | int] = {
        "client_id": client_id,
        "q": artist,
        "lat": lat,
        "lon": lng,
        "range": f"{range_mi}mi",
        "datetime_utc.gte": today.isoformat(),
        "sort": "datetime_utc.asc",
        "per_page": 5,
    }
    resp = client.get(f"{BASE}/events", params=params)
    resp.raise_for_status()
    for event in resp.json().get("events") or []:
        if not _lineup_matches(artist, event):
            continue  # `q` matched the title loosely, not this artist
        when = parse_date(event.get("datetime_local") or event.get("datetime_utc"))
        if when is None or when < today:
            continue
        venue = event.get("venue") or {}
        return ShowRow(
            artist=artist,
            date=when,
            date_token=when.strftime("%b %-d"),
            venue=venue.get("name") or "TBA",
            city=venue.get("city") or "",
        )
    return None


def _lineup_matches(artist: str, event: dict[str, Any]) -> bool:
    # Exact (case-insensitive) performer match — `q` matches titles loosely, so a
    # tribute/related act ("Bleachers Tribute Band") must not pass as the artist.
    a = artist.casefold().strip()
    names = [str(p.get("name", "")).casefold().strip() for p in (event.get("performers") or [])]
    return a in names
