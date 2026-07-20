"""HTML rendering of an edition."""

from datetime import UTC, datetime, timedelta

from still.config import load_config
from still.models import Item
from still.pipeline.editorial import (
    EditorialResult,
    FrenchEntry,
    GlossaryEntry,
    Lesson,
    Selection,
)
from still.render.html import estimate_read_time_min, render_html

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def test_render_html_includes_items_and_footnotes() -> None:
    cfg = load_config()
    item = Item(
        id="item1",
        source_name="Simon Willison",
        title="Original title",
        canonical_url="https://example.com/post",
        published_at=NOW - timedelta(hours=2),
        class_="trusted",
        section="ai",
    )
    result = EditorialResult(
        edition_headline="A quiet day in AI",
        selections=[
            Selection(
                item_id="item1",
                section="ai",
                headline="Editorial headline",
                summary="Two crisp sentences.",
            )
        ],
    )
    html = render_html(
        result, {"item1": item}, cfg, date_display="Wednesday, June 10, 2026", edition_number=1
    )
    assert "Editorial headline" in html
    assert "A quiet day in AI" in html
    assert "Simon Willison" in html
    assert "Engineering" not in html  # empty sections collapse
    assert "Vol. I &middot; No. 1 &middot; Story 1" in html  # story locator renders


def test_render_html_includes_lexicon() -> None:
    cfg = load_config()
    item = Item(
        id="item1",
        source_name="Simon Willison",
        title="t",
        canonical_url="https://example.com/post",
        published_at=NOW,
        class_="trusted",
        section="ai",
    )
    result = EditorialResult(
        edition_headline="x",
        selections=[Selection(item_id="item1", section="ai", headline="h", summary="s")],
        glossary=[GlossaryEntry(term="RAG", definition="retrieval-augmented generation")],
        french_vocab=[FrenchEntry(word="flâner", gloss="to wander without aim")],
    )
    html = render_html(
        result, {"item1": item}, cfg, date_display="Wednesday, June 10, 2026", edition_number=1
    )
    assert "Lexicon" in html
    assert "RAG" in html
    assert "flâner" in html


def _item(section: str = "ai") -> Item:
    return Item(
        id="item1",
        source_name="Simon Willison",
        title="t",
        canonical_url="https://example.com/post",
        published_at=NOW,
        class_="trusted",
        section=section,
    )


def selections_result(selections: list[Selection]) -> EditorialResult:
    return EditorialResult(edition_headline="x", selections=selections)


def test_pressing_story_renders_as_feature_marquee() -> None:
    cfg = load_config()
    result = EditorialResult(
        edition_headline="x",
        selections=[
            Selection(
                item_id="item1",
                section="ai",
                headline="Pressing head",
                summary="s",
                prominence="pressing",
                deck="A sharp one-line hook.",
            )
        ],
    )
    html = render_html(
        result, {"item1": _item()}, cfg, date_display="Wednesday, June 10, 2026", edition_number=1
    )
    assert 'class="feature"' in html  # the marquee feature well
    assert 'class="kicker"' in html  # feature kicker, e.g. "The Lead · AI & LLMs"
    assert "AI & LLMs" in html  # section title shown in the kicker (autoescape off for .j2)
    assert "A sharp one-line hook." in html  # the standfirst deck
    assert "Pressing head" in html


def test_margin_card_appears_only_with_lessons() -> None:
    cfg = load_config()
    base = [Selection(item_id="item1", section="ai", headline="h", summary="s")]
    without = render_html(
        EditorialResult(edition_headline="x", selections=base),
        {"item1": _item()},
        cfg,
        date_display="d",
        edition_number=1,
    )
    assert 'class="margin-head"' not in without  # the Margin band renders only when lessons exist
    with_lessons = render_html(
        EditorialResult(
            edition_headline="x",
            selections=base,
            lessons=[Lesson(topic="philosophy", title="Philosophy", body="Think clearly.")],
        ),
        {"item1": _item()},
        cfg,
        date_display="d",
        edition_number=1,
    )
    assert 'class="margin-head"' in with_lessons  # the full-width Margin band
    assert "The Margin" in with_lessons  # the band label
    assert "Think clearly." in with_lessons


def _n_selections(n: int) -> tuple[list[Selection], dict[str, Item]]:
    """1 marquee + (n-1) wire stories, with matching items."""
    items = {"item0": _item(section="ai")}
    selections = [Selection(item_id="item0", section="ai", headline="Marquee", summary="s")]
    for i in range(1, n):
        items[f"item{i}"] = _item(section="eng")
        selections.append(
            Selection(item_id=f"item{i}", section="eng", headline=f"H{i}", summary="s")
        )
    return selections, items


def test_edition_is_two_fixed_sheets() -> None:
    """The fixed two-page layout: exactly one p1 and one p2 sheet, always —
    even a thin edition keeps its two-page shape (stable duplex artifact)."""
    cfg = load_config()
    selections, items = _n_selections(2)
    html = render_html(
        selections_result(selections), items, cfg, date_display="d", edition_number=1
    )
    assert html.count('class="sheet p1"') == 1
    assert html.count('class="sheet p2"') == 1


def test_wire_splits_front_row_from_page_two() -> None:
    """1 marquee + 6 wire stories: exactly 4 land in the page-1 front row
    (with per-item section tags), the remaining 2 in the grouped page-2 wire."""
    cfg = load_config()
    selections, items = _n_selections(7)
    html = render_html(
        selections_result(selections), items, cfg, date_display="d", edition_number=1
    )
    assert 'class="wire wire-p1" style="column-count: 4"' in html
    p1_block = html.split('class="sheet p2"')[0]
    assert p1_block.count('class="wtag"') == 4  # one section tag per front slot
    assert 'class="wire wire-p2" style="column-count: 2"' in html  # TASK-5 clamp idiom
    assert html.count('class="wsec"') == 1  # p2 groups under one section header


def test_front_row_collapses_columns_on_a_thin_day() -> None:
    """TASK-5 idiom survives: 1 marquee + 1 wire story -> a 1-column front row
    and NO page-2 wire block (but the p2 sheet still renders for Margin/Lexicon)."""
    cfg = load_config()
    selections, items = _n_selections(2)
    html = render_html(
        selections_result(selections), items, cfg, date_display="d", edition_number=1
    )
    assert 'class="wire wire-p1" style="column-count: 1"' in html
    assert 'class="wire wire-p2"' not in html  # no page-2 wire markup (CSS rules remain)
    assert html.count('class="sheet p2"') == 1


def test_weekend_kind_sets_body_class() -> None:
    cfg = load_config()
    selections, items = _n_selections(2)
    weekday = render_html(
        selections_result(selections), items, cfg, date_display="d", edition_number=1
    )
    weekend = render_html(
        selections_result(selections),
        items,
        cfg,
        date_display="d",
        edition_number=1,
        kind="weekend",
    )
    assert '<body class="weekend">' in weekend
    assert '<body class="weekend">' not in weekday


def test_lex_cols_column_count_adapts_to_entry_count() -> None:
    """TASK-5 (b): same adaptive idiom for the Lexicon footer."""
    cfg = load_config()
    result = EditorialResult(
        edition_headline="x",
        selections=[Selection(item_id="item1", section="ai", headline="h", summary="s")],
        glossary=[GlossaryEntry(term="RAG", definition="d")],
        french_vocab=[],
    )
    html = render_html(result, {"item1": _item()}, cfg, date_display="d", edition_number=1)
    assert 'class="lex-cols" style="column-count: 1"' in html  # a single lexicon row


def test_lex_cols_column_count_caps_at_four() -> None:
    cfg = load_config()
    result = EditorialResult(
        edition_headline="x",
        selections=[Selection(item_id="item1", section="ai", headline="h", summary="s")],
        glossary=[GlossaryEntry(term=f"T{n}", definition="d") for n in range(4)],
        french_vocab=[FrenchEntry(word=f"m{n}", gloss="g") for n in range(3)],
    )
    html = render_html(result, {"item1": _item()}, cfg, date_display="d", edition_number=1)
    assert 'class="lex-cols" style="column-count: 4"' in html  # 7 rows, capped at 4


def test_read_time_scales_with_items() -> None:
    one = EditorialResult(
        edition_headline="x",
        selections=[Selection(item_id="a", section="ai", headline="h", summary="s " * 30)],
    )
    many = EditorialResult(
        edition_headline="x",
        selections=[
            Selection(item_id=str(n), section="ai", headline="h", summary="word " * 60)
            for n in range(12)
        ],
    )
    assert estimate_read_time_min(many) > estimate_read_time_min(one)
