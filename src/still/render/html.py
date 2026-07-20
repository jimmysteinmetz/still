"""RENDER stage (spec §7): edition data → print-oriented HTML.

Links render as numbered footnotes, never as taps (spec §2.4).
"""

from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from still.almanac.calendar import YourDay
from still.almanac.shows import ShowRow
from still.almanac.sports import ScoreRow
from still.almanac.weather import Weather
from still.config import StillConfig
from still.models import Item
from still.pipeline.editorial import EditorialResult
from still.pipeline.layout import EditionKind, split_wire
from still.render.icons import weather_icon
from still.render.quotes import epigraph_for


def render_html(
    result: EditorialResult,
    items_by_id: dict[str, Item],
    cfg: StillConfig,
    *,
    date_display: str,
    edition_number: int,
    kind: EditionKind = "weekday",
    weather: Weather | None = None,
    sports: list[ScoreRow] | None = None,
    shows: list[ShowRow] | None = None,
    your_day: YourDay | None = None,
) -> str:
    # Reading order follows the fixed two-page layout: marquee feature → the
    # page-1 Wire front row → the page-2 Wire (grouped by section) → Margin/
    # Lexicon. Footnotes are numbered in that order so Sources matches the read.
    section_titles = {s.id: s.title for s in cfg.sections}
    footnotes: list[str] = []

    def _row(sel: Any, *, lead: bool, section_tag: str | None = None) -> dict[str, Any]:
        item = items_by_id[sel.item_id]
        footnotes.append(item.canonical_url)
        row: dict[str, Any] = {
            "headline": sel.headline,
            "summary": sel.summary,
            "source": item.source_name,
            "ref": len(footnotes),
            "lead": lead,
            "deck": getattr(sel, "deck", "") or "",
            "pressing": sel.prominence == "pressing",
        }
        if section_tag is not None:
            row["section_tag"] = section_tag
        return row

    # The marquee/front/rest split is the fixed layout's — the SAME split
    # enforce_budget truncated against, so every story lands in the box its
    # word cap was sized for (pipeline/layout.split_wire).
    marquee_sel, front_sels, rest_sels = split_wire(result.selections, kind)
    marquee: dict[str, Any] | None = None
    if marquee_sel is not None:
        tag = section_titles.get(marquee_sel.section, marquee_sel.section)
        marquee = _row(marquee_sel, lead=True, section_tag=tag)

    # Page-1 Wire front row: up to P1_WIRE_SLOTS stories, one per column, each
    # carrying its own section tag (no grouping — they're singles).
    wire_p1 = [
        _row(s, lead=False, section_tag=section_titles.get(s.section, s.section))
        for s in front_sels
    ]

    # Page-2 Wire: the rest, grouped by section in config order, with any
    # leftover "pressing" stories leading their section (stable sort keeps the
    # model's order within each prominence tier).
    sections: list[dict[str, Any]] = []
    for section in cfg.sections:
        sels = [s for s in rest_sels if s.section == section.id]
        sels.sort(key=lambda s: s.prominence != "pressing")
        rows = [_row(sel, lead=False) for sel in sels]
        if rows:
            # key is "entries", not "items" — Jinja's attr lookup would hit dict.items
            sections.append({"title": section.title, "entries": rows})

    # Total page-2 volume, for the min(count, N) column clamp (TASK-5 idiom).
    wire_p2_count = sum(len(s["entries"]) for s in sections)

    env = Environment(
        loader=PackageLoader("still.render", "templates"),
        autoescape=select_autoescape(["html"]),
    )
    epigraph_quote, epigraph_author = epigraph_for(edition_number)
    return env.get_template("edition.html.j2").render(
        date_display=date_display,
        edition_number=edition_number,
        edition_descriptor="Weekend Edition" if kind == "weekend" else "Daily Edition",
        feature_kicker="The Weekend Read" if kind == "weekend" else "The Lead",
        is_weekend=kind == "weekend",
        edition_headline=result.edition_headline,
        marquee=marquee,
        wire_p1=wire_p1,
        sections=sections,
        wire_p2_count=wire_p2_count,
        lessons=result.lessons,
        glossary=result.glossary,
        french_vocab=result.french_vocab,
        weather=weather,
        weather_icon=Markup(weather_icon(weather.icon)) if weather else None,
        weather_precip_icon=(
            Markup(weather_icon(weather.precip_icon)) if weather and weather.precip_icon else None
        ),
        scoreboard=sports or [],
        shows=shows or [],
        your_day=your_day,
        epigraph_quote=epigraph_quote,
        epigraph_author=epigraph_author,
    )


def estimate_read_time_min(result: EditorialResult) -> int:
    """Crude: ~200 wpm over summaries plus a skim-beat per item."""
    words = sum(len(s.summary.split()) + len(s.headline.split()) for s in result.selections)
    return max(1, round(words / 200 + 0.3 * len(result.selections)))
