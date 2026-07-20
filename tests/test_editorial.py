"""Editorial budget enforcement and prompt assembly — no live LLM calls."""

from datetime import UTC, datetime, timedelta

from still.config import StillConfig, load_config
from still.models import Item
from still.pipeline.editorial import (
    EditorialResult,
    FrenchEntry,
    GlossaryEntry,
    Lesson,
    Selection,
    _finalize_french_vocab,
    _truncate_words,
    build_prompt,
    enforce_budget,
)
from still.pipeline.layout import WORD_CAPS, capacity
from still.pipeline.lessons import HARD_MAX_LESSONS, lesson_count_for, projected_item_count

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def make_item(n: int, section: str = "ai") -> Item:
    return Item(
        id=f"item{n}",
        source_name="Test",
        title=f"Story {n}",
        canonical_url=f"https://example.com/{n}",
        published_at=NOW - timedelta(hours=2),
        class_="firehose",
        section=section,
    )


def make_result(selections: list[Selection]) -> EditorialResult:
    return EditorialResult(edition_headline="Test edition", selections=selections)


def sel(n: int, section: str = "ai") -> Selection:
    return Selection(item_id=f"item{n}", section=section, headline=f"H{n}", summary="S.")


def _items_filling_all_quotas(cfg: StillConfig) -> list[Item]:
    """One item per section up to that section's quota, ids assigned in the same
    order `enumerate()` over the returned list would produce — so `sel(i, ...)`
    for `i` in `range(len(items))` lines up with `make_item(i, ...)`'s id."""
    items = []
    n = 0
    for s in cfg.sections:
        for _ in range(s.max_items):
            items.append(make_item(n, s.id))
            n += 1
    return items


def test_unknown_item_id_dropped() -> None:
    cfg = load_config()
    result = enforce_budget(
        make_result([sel(1), Selection(item_id="bogus", section="ai", headline="X", summary="Y")]),
        [make_item(1)],
        cfg,
        "weekday",
    )
    assert [s.item_id for s in result.selections] == ["item1"]


def test_duplicate_item_id_dropped() -> None:
    cfg = load_config()
    result = enforce_budget(make_result([sel(1), sel(1)]), [make_item(1)], cfg, "weekday")
    assert len(result.selections) == 1


def test_section_quota_enforced() -> None:
    cfg = load_config()
    quota = next(s.max_items for s in cfg.sections if s.id == "ai")
    n = quota + 3  # over the ai quota, under the weekday cap
    items = [make_item(i) for i in range(n)]
    result = enforce_budget(make_result([sel(i) for i in range(n)]), items, cfg, "weekday")
    assert len(result.selections) == quota


def test_unknown_section_falls_back_to_item_section() -> None:
    cfg = load_config()
    result = enforce_budget(
        make_result([Selection(item_id="item1", section="madeup", headline="H", summary="S")]),
        [make_item(1, section="eng")],
        cfg,
        "weekday",
    )
    assert result.selections[0].section == "eng"


def test_per_source_quota_enforced() -> None:
    cfg = load_config()  # Simon Willison max_items is 3
    items = []
    for n in range(5):
        item = make_item(n)
        item.source_name = "Simon Willison"
        items.append(item)
    result = enforce_budget(make_result([sel(n) for n in range(5)]), items, cfg, "weekday")
    assert len(result.selections) == 3


def test_global_budget_enforced_across_sections() -> None:
    cfg = load_config()
    cap = cfg.edition.weekend.max_items
    n = cap + 4  # split ai/eng so neither section quota binds before the global cap
    items = [make_item(i, "ai" if i % 2 == 0 else "eng") for i in range(n)]
    selections = [sel(i, "ai" if i % 2 == 0 else "eng") for i in range(n)]
    result = enforce_budget(make_result(selections), items, cfg, "weekend")
    assert len(result.selections) == cap


def test_prompt_contains_interests_quotas_and_candidates() -> None:
    cfg = load_config()
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [])
    assert "item1" in prompt
    assert f"ai: AI & LLMs (quota {cfg.sections[0].max_items})" in prompt
    assert cfg.interests[0] in prompt
    assert str(cfg.edition.weekday.max_items) in prompt  # weekday budget


def test_selection_prominence_defaults_to_brief() -> None:
    assert Selection(item_id="x", section="ai", headline="h", summary="s").prominence == "brief"


def test_prompt_contains_rotated_lesson_topic() -> None:
    cfg = load_config()
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [])
    assert "Margin" in prompt
    assert cfg.almanac.lessons.deck[0] in prompt  # first topic for edition 1


def test_prompt_contains_recent_topics_and_instruction() -> None:
    cfg = load_config()
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, ["Simon Willison SQLite tools"])
    assert "Recently covered" in prompt
    assert "Simon Willison SQLite tools" in prompt
    assert "do not re-select" in prompt.lower()


def test_prompt_omits_recent_topics_section_when_empty() -> None:
    cfg = load_config()
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [])
    assert "Recently covered" not in prompt


def test_prompt_contains_recent_lessons_and_avoid_instruction() -> None:
    cfg = load_config()
    recent_lessons = [("philosophy", "Philosophy", "The trolley problem.")]
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [], recent_lessons=recent_lessons)
    assert "Recently covered Margin lessons" in prompt
    assert "The trolley problem." in prompt
    assert "write something different" in prompt.lower()


def test_prompt_omits_recent_lessons_section_when_empty() -> None:
    cfg = load_config()
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [], recent_lessons=[])
    assert "Recently covered Margin lessons" not in prompt


def test_prompt_omits_recent_lessons_when_lessons_disabled() -> None:
    """Even with non-empty recent_lessons history, a lessons-disabled/deckless
    config must not inject the recent-lessons block — there's no Margin section
    in the prompt for it to attach to."""
    cfg = load_config()
    cfg.almanac.lessons.enabled = False
    recent_lessons = [("philosophy", "Philosophy", "The trolley problem.")]
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [], recent_lessons=recent_lessons)
    assert "Recently covered Margin lessons" not in prompt
    assert "The trolley problem." not in prompt


def test_lexicon_brief_contains_avoid_french_words() -> None:
    cfg = load_config()
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [], recent_french=["flâner"])
    assert "Do not reuse any of these recently used words" in prompt
    assert "flâner" in prompt


def test_lexicon_brief_omits_avoid_french_when_empty() -> None:
    cfg = load_config()
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [], recent_french=[])
    assert "Do not reuse any of these recently used words" not in prompt


def test_finalize_french_vocab_noop_when_no_recent() -> None:
    """At/above LEXICON_BRIEF's stated minimum of 3, nothing recent to avoid ->
    entries pass through unchanged (no drop, no top-up)."""
    entries = [
        FrenchEntry(word="flâner", gloss="to wander"),
        FrenchEntry(word="terroir", gloss="the soil, climate, and place"),
        FrenchEntry(word="bricolage", gloss="tinkering"),
    ]
    assert _finalize_french_vocab(entries, 1, []) == entries


def test_finalize_french_vocab_drops_repeats_and_tops_up() -> None:
    entries = [
        FrenchEntry(word="flâner", gloss="to wander"),
        FrenchEntry(word="terroir", gloss="the soil, climate, and place"),
    ]
    out = _finalize_french_vocab(entries, 1, ["flâner"])
    words = [e.word for e in out]
    assert "flâner" not in words
    assert "terroir" in words
    assert len(out) >= 3  # topped up to LEXICON_BRIEF's stated minimum


def test_prompt_contains_eng_style_guidance() -> None:
    """TASK-7: the eng section's config-driven `style` guidance (non-specialist
    register, vulnerability stories lead with plain-English impact) must reach
    the built prompt, next to that section's quota line."""
    cfg = load_config()
    eng = next(s for s in cfg.sections if s.id == "eng")
    assert eng.style is not None  # sanity: config/still.yaml sets it for eng
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [])
    assert eng.style in prompt
    assert "non-specialist" in prompt.lower()
    assert "plain-english impact" in prompt.lower()


def test_prompt_omits_style_line_for_section_without_style() -> None:
    """A section with no configured `style` (e.g. ai) gets no extra guidance
    line — the addition is opt-in per section, not a blanket prompt change."""
    cfg = load_config()
    ai = next(s for s in cfg.sections if s.id == "ai")
    assert ai.style is None  # sanity: config/still.yaml does not set one
    prompt = build_prompt([make_item(1)], cfg, "weekday", 1, [])
    assert "Style guidance for ai" not in prompt


def test_prompt_contains_willison_note() -> None:
    """The Simon Willison source's config-driven `note` (deprioritize routine
    SQLite/Datasette posts) must reach the built prompt, next to that source's
    quota line — mirrors Section.style."""
    cfg = load_config()
    willison = next(s for s in cfg.sources if s.name == "Simon Willison")
    assert willison.note is not None  # sanity: config/still.yaml sets it
    item = make_item(1)
    item.source_name = "Simon Willison"
    prompt = build_prompt([item], cfg, "weekday", 1, [])
    assert willison.note in prompt


def test_prompt_omits_note_line_for_source_without_note() -> None:
    """A source with no configured `note` gets no extra guidance line — the
    addition is opt-in per source, not a blanket prompt change."""
    cfg = load_config()
    source = next(s for s in cfg.sources if s.note is None)
    item = make_item(1)
    item.source_name = source.name
    prompt = build_prompt([item], cfg, "weekday", 1, [])
    assert f"Note on {source.name}" not in prompt


def test_lessons_clamped_to_budget() -> None:
    cfg = load_config()
    result = make_result([sel(1)])
    result.lessons = [Lesson(topic="t", title=f"T{n}", body="b") for n in range(9)]
    out = enforce_budget(result, [make_item(1)], cfg, "weekday")
    assert len(out.lessons) <= HARD_MAX_LESSONS  # never unbounded
    assert len(out.lessons) < 9  # the model's overflow got clamped


def test_lessons_clamp_loosens_for_a_conservative_selection() -> None:
    """TASK-5 (a): build_prompt asks for a lesson count based on a PRE-HOC pool
    projection (projected_item_count). If the LLM actually selects far fewer
    items than the pool could have supported, that pre-hoc request under-asked
    for lessons — the real page is thinner than the pool assumed. enforce_budget
    must not clamp lessons the model DID write down to the optimistic pre-hoc
    number; it should allow up to lesson_count_for(actual_count), which is
    larger because fewer items means a bigger FILL_TARGET_ITEMS shortfall."""
    cfg = load_config()
    # A pool rich enough that the pre-hoc projection sees a full day (no
    # shortfall) -> the pre-hoc request is just the base per_edition count.
    max_items = cfg.edition.weekday.max_items
    items = _items_filling_all_quotas(cfg)
    projected = projected_item_count(items, cfg, max_items)
    requested = lesson_count_for(cfg, projected)
    assert requested == cfg.almanac.lessons.per_edition  # sanity: pool looks full
    # ...but the model conservatively selects just one item.
    result = make_result([sel(0, items[0].section)])
    actual = lesson_count_for(cfg, 1)
    assert actual > requested  # the thin real selection justifies more lessons
    # The model wrote more lessons than the pre-hoc request — they should survive.
    result.lessons = [Lesson(topic="t", title=f"T{n}", body="b") for n in range(actual)]
    out = enforce_budget(result, items, cfg, "weekday")
    assert len(out.lessons) == actual  # not clamped down to the optimistic pre-hoc count


def test_lessons_clamp_unaffected_when_selection_matches_projection() -> None:
    """TASK-5 (a), the other direction: when the actual selection is at least as
    rich as the pool projection assumed (the normal/full-day case), the post-hoc
    recompute must not change behavior — max(requested, actual) should just be
    the original pre-hoc count, since lesson_count_for is non-increasing in item
    count and actual selections can never exceed the pool projection."""
    cfg = load_config()
    max_items = cfg.edition.weekday.max_items
    items = _items_filling_all_quotas(cfg)
    projected = projected_item_count(items, cfg, max_items)
    requested = lesson_count_for(cfg, projected)
    # The model selects everything the pool can support (a full, busy day).
    result = make_result([sel(i, it.section) for i, it in enumerate(items)])
    result.lessons = [Lesson(topic="t", title=f"T{n}", body="b") for n in range(HARD_MAX_LESSONS)]
    out = enforce_budget(result, items, cfg, "weekday")
    assert len(out.lessons) == requested  # unchanged from the pre-hoc pool estimate


# --- fixed-layout word caps (pipeline/layout.py WORD_CAPS, enforced here) ---

SENTENCE = "alpha beta gamma delta epsilon zeta eta theta iota kappa."  # 10 words


def prose(sentences: int) -> str:
    return " ".join([SENTENCE] * sentences)


def test_truncate_words_under_cap_unchanged() -> None:
    text = prose(3)
    assert _truncate_words(text, 30) == text
    assert _truncate_words(text, 31) == text


def test_truncate_words_drops_whole_trailing_sentences() -> None:
    # 5 sentences / 50 words at a 35-word cap -> keep 3 whole sentences (30
    # words), never a mid-sentence cut, no ellipsis.
    out = _truncate_words(prose(5), 35)
    assert out == prose(3)
    assert not out.endswith("…")


def test_truncate_words_hard_cuts_a_run_on() -> None:
    # A single 40-word sentence can't be sentence-truncated to 15 — hard word
    # cut with a visible ellipsis is the fallback.
    run_on = "word " * 39 + "word."
    out = _truncate_words(run_on, 15)
    assert out == "word " * 14 + "word…"


def test_enforce_budget_truncates_by_layout_tier() -> None:
    """The marquee, the 4 front-row stories, and page-2 briefs each get their
    own WORD_CAPS allowance; decks, lessons, and the Lexicon are capped too."""
    cfg = load_config()
    caps = WORD_CAPS["weekday"]
    n = 8  # 1 marquee + 4 front + 3 briefs, under the ai(6)+eng(8) quotas
    items = [make_item(i, "ai" if i < 4 else "eng") for i in range(n)]
    selections = []
    for i in range(n):
        s = sel(i, "ai" if i < 4 else "eng")
        s.prominence = "pressing" if i == 0 else "brief"
        s.summary = prose(30)  # 300 words, over every cap
        selections.append(s)
    selections[0].deck = "deck " * 29 + "deck"  # 30-word run-on, over the deck cap
    result = make_result(selections)
    result.lessons = [Lesson(topic="t", title="T", body=prose(10))]
    result.glossary = [GlossaryEntry(term="X", definition=prose(4))]
    result.french_vocab = [FrenchEntry(word="mot", gloss=prose(3))]
    out = enforce_budget(result, items, cfg, "weekday")

    def words(text: str) -> int:
        return len(text.split())

    by_id = {s.item_id: s for s in out.selections}
    assert words(by_id["item0"].summary) == caps["marquee"] // 10 * 10  # whole sentences
    assert words(by_id["item0"].deck) <= caps["deck"] + 1  # hard cut carries "…"
    for front_id in ("item1", "item2", "item3", "item4"):
        assert words(by_id[front_id].summary) <= caps["front"]
    for brief_id in ("item5", "item6", "item7"):
        assert words(by_id[brief_id].summary) <= caps["brief"]
    assert words(out.lessons[0].body) <= caps["lesson"]
    assert words(out.glossary[0].definition) <= caps["gloss"]
    assert words(out.french_vocab[0].gloss) <= caps["french"]


def test_capacity_clamps_even_if_config_asks_for_more() -> None:
    """still.yaml can lower the budget below the fixed layout's capacity but
    never raise it above — the geometry is the harder ceiling."""
    cfg = load_config()
    cfg.edition.weekday.max_items = 30  # config schema allows it; layout doesn't
    items = _items_filling_all_quotas(cfg)
    selections = [sel(i, items[i].section) for i in range(25)]
    out = enforce_budget(make_result(selections), items, cfg, "weekday")
    assert len(out.selections) == capacity("weekday")
