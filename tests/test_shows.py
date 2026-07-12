"""Upcoming Shows fetch against a mocked SeatGeek API — no live network."""

from datetime import date, timedelta

import httpx

from still.almanac import shows

TODAY = date(2026, 6, 24)
NYC = {"lat": 40.7128, "lng": -74.0060, "range_mi": 40}


def _event(performer: str, delta: int, venue: str, city: str = "New York") -> dict[str, object]:
    when = (TODAY + timedelta(days=delta)).isoformat()
    return {
        "title": performer,
        "datetime_local": f"{when}T20:00:00",
        "datetime_utc": f"{when}T00:00:00",
        "venue": {"name": venue, "city": city, "state": "NY"},
        "performers": [{"name": performer, "slug": performer.lower().replace(" ", "-")}],
    }


# Keyed by the `q` search term the fetch sends per artist.
EVENTS: dict[str, list[dict[str, object]]] = {
    "Lake Street Dive": [_event("Lake Street Dive", 39, "Beacon Theatre")],
    "Vulfpeck": [_event("Vulfpeck", 77, "Madison Square Garden")],
    # `q` matched a tribute act, not the artist — must be filtered out by lineup match.
    "Bleachers": [_event("Bleachers Tribute Band", 10, "Some Bar")],
    "Phoebe Bridgers": [],  # nothing in range
}


def handler(request: httpx.Request) -> httpx.Response:
    if not request.url.path.endswith("/events"):
        return httpx.Response(404)
    q = request.url.params.get("q", "")
    if q == "BOOM":  # used to exercise the per-artist error path
        return httpx.Response(500)
    return httpx.Response(200, json={"events": EVENTS.get(q, [])})


def _client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _fetch(artists: list[str], client_id: str | None = "test-id") -> list[shows.ShowRow]:
    return shows.fetch_shows(artists, _client(), today=TODAY, client_id=client_id, **NYC)


def test_no_client_id_hides_card() -> None:
    assert _fetch(["Lake Street Dive"], client_id=None) == []


def test_next_show_parsed() -> None:
    rows = _fetch(["Lake Street Dive"])
    assert len(rows) == 1
    assert rows[0].artist == "Lake Street Dive"
    assert rows[0].venue == "Beacon Theatre"
    assert rows[0].date == TODAY + timedelta(days=39)
    assert rows[0].date_token  # "Aug 2"-style label


def test_rows_sorted_by_date() -> None:
    rows = _fetch(["Vulfpeck", "Lake Street Dive"])  # Vulf later, LSD sooner
    assert [r.artist for r in rows] == ["Lake Street Dive", "Vulfpeck"]


def test_lineup_mismatch_filtered() -> None:
    # "Bleachers Tribute Band" must not satisfy a search for "Bleachers".
    assert _fetch(["Bleachers"]) == []


def test_artist_with_no_shows_skipped() -> None:
    assert _fetch(["Phoebe Bridgers"]) == []


def test_failing_lookup_skips_only_that_artist() -> None:
    rows = _fetch(["BOOM", "Lake Street Dive"])
    assert [r.artist for r in rows] == ["Lake Street Dive"]


def test_geo_and_date_params_sent() -> None:
    seen: list[httpx.URL] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"events": []})

    client = httpx.Client(transport=httpx.MockTransport(spy))
    shows.fetch_shows(["X"], client, today=TODAY, client_id="k", **NYC)
    p = seen[0].params
    assert p.get("range") == "40mi"
    assert p.get("client_id") == "k"
    assert p.get("datetime_utc.gte") == TODAY.isoformat()
