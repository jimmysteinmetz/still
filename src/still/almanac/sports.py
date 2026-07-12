"""Your Teams / Scoreboard — ESPN public API (spec §4A, §6).

ESPN's site API needs no key and hands us, in one call per team, the full season
schedule with scores, statuses, and — crucially — a crisp logo URL for both our team
and every opponent (`competitor.team.logos[0].href`). A motorsport `Series` reads its
next race from the league scoreboard.

Whether a team renders is derived purely from its schedule dates, so there's no season
calendar to maintain:

  * next fixture > 14 days away (or none)  → off-season, row collapses (returns None)
  * next within 14 days + a recent result  → in-season: show result + next fixture
  * next within 14 days + no recent result → countdown to the season opener

Each entity is fetched in isolation: a dead lookup skips that row, never the whole card
(spec §2 — sources fail gracefully).
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from still.almanac.util import parse_date
from still.config import Series, Team
from still.render import badges

logger = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports"

TEAM_WINDOW_DAYS = 14  # render a team only if its next fixture is within this
RECENT_LAST_DAYS = 16  # a last result this recent means "in season" (covers byes)
RACE_WINDOW_DAYS = 21  # races are ~biweekly, so look a little further ahead

Mode = Literal["result", "countdown", "race"]


class ScoreRow(BaseModel):
    """One render-ready Scoreboard line (a mini-scorebug)."""

    label: str  # team short label — alt text and fallback when a crest is missing
    us_badge: str | None  # our crest, monochrome data-URI
    mode: Mode
    score: str | None = None  # "0–2" read as us–them (result mode)
    last_opp_badge: str | None = None  # opponent crest in the last result
    next_token: str = ""  # "Sat @", "Sun v", "opens in 9d v", or a race countdown
    next_opp_badge: str | None = None  # opponent crest in the next fixture
    venue: str | None = None  # race location (race mode)


def fetch_sports(
    teams: list[Team],
    series: list[Series],
    client: httpx.Client,
    cache_dir: Path,
    *,
    today: date,
) -> list[ScoreRow]:
    """Build the Scoreboard: in-season teams + upcoming races.

    Teams and series share one `order` field (see `config.Team`/`config.Series`),
    so they're merged into a single sequence and sorted by it before rendering —
    a series can land between two teams instead of always trailing all teams.
    Ties fall back to teams-then-series, in config order (stable sort). Empty →
    card hides.
    """
    entries: list[Team | Series] = [t for t in teams if t.enabled] + [
        s for s in series if s.enabled
    ]
    entries.sort(key=lambda e: e.order)
    rows: list[ScoreRow] = []
    for entry in entries:
        try:
            row = (
                _team_row(entry, client, cache_dir, today)
                if isinstance(entry, Team)
                else _series_row(entry, client, cache_dir, today)
            )
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            logger.warning("sports: %s skipped: %s", entry.name, e)
            continue
        if row:
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- teams


def _team_row(team: Team, client: httpx.Client, cache_dir: Path, today: date) -> ScoreRow | None:
    events = _schedule(client, team, today)
    past = [e for e in events if e["completed"] and e["date"] and e["date"] <= today]
    future = [e for e in events if not e["completed"] and e["date"] and e["date"] >= today]
    last = max(past, key=lambda e: e["date"]) if past else None
    nxt = min(future, key=lambda e: e["date"]) if future else None

    mode = _team_mode(last["date"] if last else None, nxt["date"] if nxt else None, today)
    if mode is None:
        return None

    def crest(event: dict[str, Any] | None, side: str) -> str | None:
        return badges.to_mono_data_uri(_logo(event, side), client, cache_dir) if event else None

    label = team.short or team.name
    us_badge = crest(nxt or last, "us")

    if mode == "result":
        assert last is not None and nxt is not None
        return ScoreRow(
            label=label,
            us_badge=us_badge,
            mode="result",
            score=_score(last["us"], last["opp"]),
            last_opp_badge=crest(last, "opp"),
            next_token=f"{nxt['date'].strftime('%a')} {_mark(nxt)}",
            next_opp_badge=crest(nxt, "opp"),
        )

    assert nxt is not None  # countdown mode guarantees an upcoming fixture
    days = (nxt["date"] - today).days
    return ScoreRow(
        label=label,
        us_badge=us_badge,
        mode="countdown",
        next_token=f"opens in {days}d {_mark(nxt)}",
        next_opp_badge=crest(nxt, "opp"),
    )


def _team_mode(last_date: date | None, next_date: date | None, today: date) -> Mode | None:
    if next_date is None:
        return None
    if not 0 <= (next_date - today).days <= TEAM_WINDOW_DAYS:
        return None  # off-season (or stale past fixture)
    if last_date is not None and 0 <= (today - last_date).days <= RECENT_LAST_DAYS:
        return "result"
    return "countdown"


def _schedule(client: httpx.Client, team: Team, today: date) -> list[dict[str, Any]]:
    params: dict[str, int] = {}
    if team.espn_path.startswith("soccer/"):
        # ESPN labels a soccer season by its August start year; the default
        # schedule is often empty, so pin it.
        params["season"] = today.year if today.month >= 7 else today.year - 1
    resp = client.get(f"{BASE}/{team.espn_path}/teams/{team.espn_id}/schedule", params=params)
    resp.raise_for_status()
    parsed = [_parse_event(e, team.espn_id) for e in (resp.json().get("events") or [])]
    return [e for e in parsed if e]


def _parse_event(event: dict[str, Any], espn_id: int) -> dict[str, Any] | None:
    comps = event.get("competitions")
    if not comps:
        return None
    comp = comps[0]
    competitors = comp.get("competitors") or []
    us = next((c for c in competitors if str(c.get("team", {}).get("id")) == str(espn_id)), None)
    opp = next((c for c in competitors if c is not us), None)
    if us is None or opp is None:
        return None
    return {
        "date": parse_date(event.get("date")),
        "completed": bool(comp.get("status", {}).get("type", {}).get("completed")),
        "us": us,
        "opp": opp,
    }


# -------------------------------------------------------------------------- series


def _series_row(s: Series, client: httpx.Client, cache_dir: Path, today: date) -> ScoreRow | None:
    # The bare scoreboard only holds the current race week; ?dates=<year> returns
    # the whole season calendar, so we can find the *next* race.
    resp = client.get(f"{BASE}/{s.espn_path}/scoreboard", params={"dates": today.year})
    resp.raise_for_status()
    data = resp.json()
    dated = [(d, e) for e in data.get("events", []) if (d := parse_date(e.get("date")))]
    upcoming = sorted((pair for pair in dated if pair[0] >= today), key=lambda p: p[0])
    if not upcoming:
        return None
    race_date, race = upcoming[0]
    days = (race_date - today).days
    if days > RACE_WINDOW_DAYS:
        return None
    name = race.get("shortName") or race.get("name") or "TBA"
    venue = name.removeprefix("Grand Prix of ").strip() or name
    return ScoreRow(
        label=s.short or s.name,
        us_badge=badges.to_mono_data_uri(_series_logo(data), client, cache_dir),
        mode="race",
        venue=venue,
        next_token="today" if days == 0 else f"in {days}d",
    )


# ------------------------------------------------------------------------- helpers


def _mark(event: dict[str, Any]) -> str:
    return "v" if event["us"].get("homeAway") == "home" else "@"


def _logo(event: dict[str, Any], side: str) -> str:
    competitor = event["us"] if side == "us" else event["opp"]
    logos = competitor.get("team", {}).get("logos") or []
    return logos[0].get("href", "") if logos else ""


def _series_logo(scoreboard: dict[str, Any]) -> str:
    leagues = scoreboard.get("leagues") or []
    logos = (leagues[0].get("logos") if leagues else None) or []
    return logos[0].get("href", "") if logos else ""


def _score(us: dict[str, Any], opp: dict[str, Any]) -> str | None:
    a, b = _score_val(us), _score_val(opp)
    return f"{a}–{b}" if a is not None and b is not None else None


def _score_val(competitor: dict[str, Any]) -> str | None:
    s = competitor.get("score")
    if isinstance(s, dict):
        val = s.get("displayValue")
        return str(val) if val not in (None, "") else None
    return str(s) if s not in (None, "") else None
