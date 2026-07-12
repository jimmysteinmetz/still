"""Scoreboard fetch against a mocked ESPN API — schedule JSON, scoreboard, and logos."""

import io
from datetime import date, timedelta

import httpx
from PIL import Image

from still.almanac import sports
from still.config import Series, Team

TODAY = date(2026, 1, 15)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (12, 12), (10, 10, 10, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _competitor(team_id: int, home_away: str, score: int | None) -> dict[str, object]:
    return {
        "homeAway": home_away,
        "score": {"displayValue": str(score)} if score is not None else None,
        "team": {
            "id": str(team_id),
            "abbreviation": f"A{team_id}",
            "logos": [{"href": f"https://a.espncdn.com/logos/{team_id}.png"}],
        },
    }


def _ev(
    our_id: int,
    delta: int,
    our_ha: str,
    opp_id: int,
    *,
    our_score: int | None = None,
    opp_score: int | None = None,
    completed: bool,
) -> dict[str, object]:
    when = (TODAY + timedelta(days=delta)).isoformat() + "T18:00Z"
    opp_ha = "away" if our_ha == "home" else "home"
    return {
        "date": when,
        "competitions": [
            {
                "status": {
                    "type": {"state": "post" if completed else "pre", "completed": completed}
                },
                "competitors": [
                    _competitor(our_id, our_ha, our_score),
                    _competitor(opp_id, opp_ha, opp_score),
                ],
            }
        ],
    }


SCHED: dict[str, list[dict[str, object]]] = {
    "100": [  # in-season: recent win at home, next away
        _ev(100, -3, "home", 101, our_score=110, opp_score=99, completed=True),
        _ev(100, 4, "away", 102, completed=False),
    ],
    "110": [  # in-season: recent win away, next home
        _ev(110, -3, "away", 111, our_score=27, opp_score=20, completed=True),
        _ev(110, 2, "home", 112, completed=False),
    ],
    "200": [  # stale last + opener in 9 days → countdown
        _ev(200, -60, "home", 201, our_score=1, opp_score=0, completed=True),
        _ev(200, 9, "home", 202, completed=False),
    ],
    "300": [_ev(300, 40, "home", 303, completed=False)],  # far off → off-season
}

SCOREBOARD = [
    {
        "date": (TODAY + timedelta(days=6)).isoformat() + "T20:00Z",
        "shortName": "Grand Prix of Long Beach",
    }
]
SERIES_LEAGUES = [{"logos": [{"href": "https://a.espncdn.com/logos/series.png"}]}]


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/logos/" in path:
        return httpx.Response(200, content=_png())
    if path.endswith("/scoreboard"):
        return httpx.Response(200, json={"events": SCOREBOARD, "leagues": SERIES_LEAGUES})
    if path.endswith("/schedule"):
        team_id = path.split("/teams/")[1].split("/")[0]
        if team_id == "500":
            return httpx.Response(500)
        return httpx.Response(200, json={"events": SCHED.get(team_id, [])})
    return httpx.Response(404)


def _client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _team(id_: int, *, path: str = "basketball/nba", enabled: bool = True, order: int = 0) -> Team:
    return Team(
        name=f"T{id_}",
        short=f"T{id_}",
        league="X",
        espn_path=path,
        espn_id=id_,
        enabled=enabled,
        order=order,
    )


def test_in_season_home_team(tmp_path) -> None:  # type: ignore[no-untyped-def]
    rows = sports.fetch_sports([_team(100)], [], _client(), tmp_path, today=TODAY)
    assert len(rows) == 1
    r = rows[0]
    assert r.mode == "result"
    assert r.score == "110–99"  # us(home)–them
    assert r.us_badge and r.last_opp_badge and r.next_opp_badge
    assert r.next_token.endswith("@")  # next fixture is away


def test_away_team_score_orientation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    rows = sports.fetch_sports([_team(110)], [], _client(), tmp_path, today=TODAY)
    assert rows[0].score == "27–20"  # we were away (27), opponent home (20)
    assert rows[0].next_token.endswith("v")  # next fixture is home


def test_countdown_team(tmp_path) -> None:  # type: ignore[no-untyped-def]
    rows = sports.fetch_sports([_team(200)], [], _client(), tmp_path, today=TODAY)
    assert len(rows) == 1
    assert rows[0].mode == "countdown"
    assert rows[0].score is None
    assert "opens in 9d" in rows[0].next_token


def test_offseason_team_hidden(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert sports.fetch_sports([_team(300)], [], _client(), tmp_path, today=TODAY) == []


def test_series_race_row(tmp_path) -> None:  # type: ignore[no-untyped-def]
    series = [Series(name="IndyCar", short="INDYCAR", espn_path="racing/irl")]
    rows = sports.fetch_sports([], series, _client(), tmp_path, today=TODAY)
    assert len(rows) == 1
    assert rows[0].mode == "race"
    assert rows[0].venue == "Long Beach"  # "Grand Prix of " stripped
    assert rows[0].next_token == "in 6d"
    assert rows[0].us_badge  # series logo from leagues[].logos


def test_series_interleaves_between_teams_by_order(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Teams and series share one `order` field (TASK-8) — a series should be
    # able to land between two teams instead of always trailing every team.
    teams = [_team(100, order=1), _team(110, order=3)]
    series = [Series(name="IndyCar", short="INDYCAR", espn_path="racing/irl", order=2)]
    rows = sports.fetch_sports(teams, series, _client(), tmp_path, today=TODAY)
    assert [r.label for r in rows] == ["T100", "INDYCAR", "T110"]


def test_offseason_team_collapses_out_of_interleaved_order(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # An off-season team disappears from the merged, ordered list entirely —
    # it doesn't leave a gap or otherwise disturb the surrounding order.
    teams = [_team(100, order=1), _team(300, order=2), _team(110, order=4)]
    series = [Series(name="IndyCar", short="INDYCAR", espn_path="racing/irl", order=3)]
    rows = sports.fetch_sports(teams, series, _client(), tmp_path, today=TODAY)
    assert [r.label for r in rows] == ["T100", "INDYCAR", "T110"]


def test_failing_lookup_skips_only_that_entity(tmp_path) -> None:  # type: ignore[no-untyped-def]
    rows = sports.fetch_sports([_team(500), _team(100)], [], _client(), tmp_path, today=TODAY)
    assert [r.label for r in rows] == ["T100"]  # 500 errored out, 100 still rendered


def test_disabled_entities_are_skipped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    rows = sports.fetch_sports([_team(100, enabled=False)], [], _client(), tmp_path, today=TODAY)
    assert rows == []


def test_soccer_pins_season(tmp_path) -> None:  # type: ignore[no-untyped-def]
    seen: list[httpx.URL] = []

    def soccer_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"events": []})

    client = httpx.Client(transport=httpx.MockTransport(soccer_handler))
    sports.fetch_sports([_team(367, path="soccer/eng.1")], [], client, tmp_path, today=TODAY)
    assert seen and seen[0].params.get("season") == "2025"  # Jan → previous Aug-start year


def test_score_and_mark_units() -> None:
    event = {
        "us": _competitor(100, "away", 110),
        "opp": _competitor(102, "home", 99),
    }
    assert sports._score(event["us"], event["opp"]) == "110–99"
    assert sports._mark(event) == "@"
