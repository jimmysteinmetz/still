"""Rotating "Margin" lesson topics — CODE picks, the editorial LLM writes.

A topic deck lives in config (`almanac.lessons.deck`). Each edition, code rotates
deterministically by `edition_number` (mirrors `render/quotes.epigraph_for`) to pick
the topics; their briefs are injected into the editorial prompt. The LLM writes a
short lesson per topic — it never chooses the topics. On a thin-news day the lesson
count expands (up to `HARD_MAX_LESSONS`) so educational content helps fill the page
instead of padding with weak news. Lives in `pipeline/` because only editorial
consumes it (quotes.py lives in `render/` for the same reason).
"""

from still.config import StillConfig
from still.models import Item

# Known topic keys → a richer one-line brief steering the LLM. Unknown keys fall back
# to the humanized raw string, so any word dropped into the deck still works.
# `sports_trivia` is augmented at runtime with the reader's followed teams/series.
TOPIC_BRIEFS: dict[str, str] = {
    "cybersecurity": (
        "a practical computer-security concept, threat, or defensive habit worth knowing"
    ),
    "french_culture": (
        "an aspect of French culture, history, or daily life a Francophile would savor"
    ),
    "philosophy": (
        "a philosophical idea, school, or thinker, explained so it lands in everyday terms"
    ),
    "ny_knowledge": (
        "something about New York City — its history, geography, transit, or neighborhoods"
    ),
    "sports_trivia": "an engaging piece of sports trivia or history",
    "vocabulary": (
        "an uncommon but useful English word, with its meaning and a vivid example of use"
    ),
    "world_history": "a consequential moment or pattern in world history, told as a short story",
}

# Roughly the item count that fills two dense pages. Below it, lessons expand to
# absorb the slack — one extra lesson per this many items short.
FILL_TARGET_ITEMS = 18
ITEMS_PER_EXTRA_LESSON = 4
# Hard ceiling on lessons even on the thinnest day (also bounded by deck size). The
# Margin box stays well under a column height at this count, so break-inside:avoid
# is safe (see the weasyprint multicol note in CLAUDE.md).
HARD_MAX_LESSONS = 5


def topics_for(edition_number: int, cfg: StillConfig, count: int | None = None) -> list[str]:
    """Pick this edition's topic keys — deterministic, rotates daily, walks the deck
    in order (mirrors quotes.epigraph_for's index math). `count` defaults to the
    configured base `per_edition`; pass an expanded count to fill a thin day."""
    lessons = cfg.almanac.lessons
    deck = lessons.deck
    if not lessons.enabled or not deck:
        return []
    n = min(lessons.per_edition if count is None else count, len(deck))
    start = (edition_number - 1) % len(deck)
    return [deck[(start + i) % len(deck)] for i in range(n)]


def projected_item_count(candidates: list[Item], cfg: StillConfig, max_items: int) -> int:
    """A cheap upper-bound on how many news items this pool can yield: per section,
    the lesser of its quota and its available candidates, capped by the edition
    budget. Used only as a 'is the day thin?' signal for lesson expansion."""
    per_section: dict[str, int] = {}
    for it in candidates:
        per_section[it.section] = per_section.get(it.section, 0) + 1
    total = sum(min(s.max_items, per_section.get(s.id, 0)) for s in cfg.sections)
    return min(max_items, total)


def lesson_count_for(cfg: StillConfig, projected_items: int) -> int:
    """How many lessons to run: the base `per_edition`, plus one per
    ITEMS_PER_EXTRA_LESSON the day falls short of FILL_TARGET_ITEMS, clamped to the
    deck size and HARD_MAX_LESSONS. Zero when lessons are disabled/deckless."""
    lessons = cfg.almanac.lessons
    if not lessons.enabled or not lessons.deck:
        return 0
    shortfall = max(0, FILL_TARGET_ITEMS - projected_items)
    extra = shortfall // ITEMS_PER_EXTRA_LESSON
    return min(lessons.per_edition + extra, HARD_MAX_LESSONS, len(lessons.deck))


def brief_for(topic: str, cfg: StillConfig) -> str:
    """The instruction the LLM gets for one topic. Known keys get a richer brief;
    unknown keys fall back to the humanized raw string. `sports_trivia` references
    the reader's configured teams/series so trivia targets what they follow."""
    base = TOPIC_BRIEFS.get(topic, topic.replace("_", " "))
    if topic == "sports_trivia":
        followed = [t.name for t in cfg.almanac.teams if t.enabled]
        followed += [s.name for s in cfg.almanac.series if s.enabled]
        if followed:
            base = f"{base}, ideally about one of the reader's teams/series: {', '.join(followed)}"
    return base
