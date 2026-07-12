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


def test_wire_column_count_adapts_to_item_count() -> None:
    """TASK-5 (b): .wire's column-count should collapse to the actual number of
    Wire entries (marquee excluded) rather than always spreading across a fixed
    4 — a thin trailing page with only 1-2 leftover items used to strand them
    across 4 narrow columns instead of 1-2 wide ones."""
    cfg = load_config()
    items = {f"item{n}": _item(section="eng") for n in range(1, 3)}
    # One marquee (not in the Wire) + 2 Wire items.
    selections = [
        Selection(item_id="item1", section="ai", headline="Marquee", summary="s"),
        Selection(item_id="item2", section="eng", headline="Wire one", summary="s"),
    ]
    items["item1"] = _item(section="ai")
    html = render_html(
        selections_result(selections), items, cfg, date_display="d", edition_number=1
    )
    assert 'class="wire" style="column-count: 1"' in html  # only 1 real Wire entry


def test_wire_column_count_caps_at_four() -> None:
    cfg = load_config()
    items = {"item0": _item(section="ai")}
    selections = [Selection(item_id="item0", section="ai", headline="Marquee", summary="s")]
    for n in range(1, 7):  # 6 Wire items, well past the 4-column ceiling
        items[f"item{n}"] = _item(section="eng")
        selections.append(
            Selection(item_id=f"item{n}", section="eng", headline=f"H{n}", summary="s")
        )
    html = render_html(
        selections_result(selections), items, cfg, date_display="d", edition_number=1
    )
    assert 'class="wire" style="column-count: 4"' in html  # capped, never wider than 4


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
