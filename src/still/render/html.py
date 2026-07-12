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
from still.render.icons import weather_icon
from still.render.quotes import epigraph_for


def render_html(
    result: EditorialResult,
    items_by_id: dict[str, Item],
    cfg: StillConfig,
    *,
    date_display: str,
    edition_number: int,
    kind: str = "weekday",
    weather: Weather | None = None,
    sports: list[ScoreRow] | None = None,
    shows: list[ShowRow] | None = None,
    your_day: YourDay | None = None,
) -> str:
    # Reading order is the marquee feature → The Wire (everything else, grouped by
    # section) → The Margin/Lexicon at the foot. Footnotes are numbered in that
    # order — marquee first, then section by section — so Sources matches the read.
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

    # Marquee anchors the feature well: the first "pressing" story, or — if a
    # malfunctioning model flagged none — simply the first selection, so the front
    # always has a lead rather than an empty well.
    marquee: dict[str, Any] | None = None
    marquee_id: str | None = None
    lead_sel = next((s for s in result.selections if s.prominence == "pressing"), None)
    if lead_sel is None and result.selections:
        lead_sel = result.selections[0]
    if lead_sel is not None:
        marquee_id = lead_sel.item_id
        tag = section_titles.get(lead_sel.section, lead_sel.section)
        marquee = _row(lead_sel, lead=True, section_tag=tag)

    # The Wire: every other selection, grouped by section in config order, with any
    # remaining "pressing" stories leading their section (stable sort keeps the
    # model's order within each prominence tier).
    sections: list[dict[str, Any]] = []
    for section in cfg.sections:
        sels = [s for s in result.selections if s.section == section.id and s.item_id != marquee_id]
        sels.sort(key=lambda s: s.prominence != "pressing")
        rows = [_row(sel, lead=False) for sel in sels]
        if rows:
            # key is "entries", not "items" — Jinja's attr lookup would hit dict.items
            sections.append({"title": section.title, "entries": rows})

    # Total Wire volume across all sections, used by the template to size the
    # .wire column-count (min(wire_count, 4), same idiom as .margin-cols) — a
    # thin trailing page's last couple of items collapse to fewer, wider columns
    # instead of stranding across 4 narrow ones (TASK-5).
    wire_count = sum(len(s["entries"]) for s in sections)

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
        sections=sections,
        wire_count=wire_count,
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
