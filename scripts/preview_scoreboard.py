"""Preview the Scoreboard + masthead design with real ESPN crests.

Renders a populated sample edition to ``data/scoreboard-preview.pdf`` so you can
eyeball the layout without waiting for teams to be in-season or running the LLM
editorial pass. Each followed team shows its most recent real result (scanning the
last couple of seasons), and the series shows its next race.

    uv run scripts/preview_scoreboard.py && open data/scoreboard-preview.pdf

(Prefix with DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib to force WeasyPrint on a
Mac; otherwise it falls back to headless Chrome, which is fine.)
"""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from still.almanac import sports
from still.almanac.sports import ScoreRow
from still.config import Team, load_config
from still.models import Item
from still.pipeline.editorial import EditorialResult, Selection
from still.render import badges
from still.render.html import render_html
from still.render.pdf import html_to_pdf

CACHE = Path("data/badges")


def _latest_result(team: Team, client: httpx.Client) -> dict[str, Any] | None:
    """Most recent completed game for a team, scanning the current + prior season."""
    today = date.today()
    for season in (today.year, today.year - 1):
        params: dict[str, int] = {"season": season}
        if not team.espn_path.startswith("soccer/"):
            params["seasontype"] = 2  # regular season
        resp = client.get(
            f"{sports.BASE}/{team.espn_path}/teams/{team.espn_id}/schedule", params=params
        )
        events = [
            e
            for e in (sports._parse_event(x, team.espn_id) for x in resp.json().get("events", []))
            if e and e["completed"]
        ]
        if events:
            return max(events, key=lambda e: e["date"])
    return None


def _row(team: Team, client: httpx.Client) -> ScoreRow | None:
    last = _latest_result(team, client)
    if not last:
        return None

    def crest(side: str) -> str | None:
        return badges.to_mono_data_uri(sports._logo(last, side), client, CACHE)

    return ScoreRow(
        label=team.short or team.name,
        us_badge=crest("us"),
        mode="result",
        score=sports._score(last["us"], last["opp"]),
        last_opp_badge=crest("opp"),
        next_token=f"{last['date'].strftime('%a')} {sports._mark(last)}",
        next_opp_badge=crest("opp"),
    )


cfg = load_config()
rows: list[ScoreRow] = []
with httpx.Client(timeout=25, headers={"User-Agent": "still/0.1 preview"}) as client:
    for team in cfg.almanac.teams:
        if not team.enabled:
            continue
        try:
            row = _row(team, client)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            print(f"skip {team.short}: {e}")
            continue
        if row:
            rows.append(row)
    rows += sports.fetch_sports([], cfg.almanac.series, client, CACHE, today=date.today())

# Minimal sample content so the three columns aren't empty.
result = EditorialResult(
    edition_headline="Scoreboard & Masthead Preview",
    selections=[
        Selection(
            item_id="i0",
            section="ai",
            headline="Sample headline for layout tuning",
            summary="Placeholder body copy so the columns fill out and the design reads true. " * 6,
        )
    ],
)
items = {
    "i0": Item(
        id="i0",
        source_name="Sample",
        title="t",
        canonical_url="https://example.com/a",
        published_at=datetime.now(UTC),
        class_="trusted",
        section="ai",
    )
}
html = render_html(
    result,
    items,
    cfg,
    date_display=date.today().strftime("%A, %B %-d, %Y"),
    edition_number=7,
    sports=rows,
)
out = Path("data/scoreboard-preview.pdf")
engine = html_to_pdf(html, out)
print(f"engine={engine}  rows={[r.label for r in rows]}  -> {out}")
