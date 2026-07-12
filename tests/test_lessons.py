"""Rotating "Margin" lesson selection — pure code, no LLM."""

from datetime import UTC, datetime

from still.config import load_config
from still.models import Item
from still.pipeline.lessons import (
    FILL_TARGET_ITEMS,
    HARD_MAX_LESSONS,
    brief_for,
    lesson_count_for,
    projected_item_count,
    topics_for,
)

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)


def _items(section: str, n: int) -> list[Item]:
    return [
        Item(
            id=f"{section}{i}",
            source_name="x",
            title="t",
            canonical_url=f"https://example.com/{section}/{i}",
            published_at=NOW,
            class_="firehose",
            section=section,
        )
        for i in range(n)
    ]


def test_topics_rotate_deterministically() -> None:
    cfg = load_config()
    deck = cfg.almanac.lessons.deck
    per = cfg.almanac.lessons.per_edition
    assert topics_for(1, cfg) == deck[:per]
    # consecutive editions shift the window by one
    assert topics_for(2, cfg) == [deck[(1 + i) % len(deck)] for i in range(per)]
    # a full cycle through the deck wraps back to the start
    assert topics_for(len(deck) + 1, cfg) == topics_for(1, cfg)


def test_topics_count_override() -> None:
    cfg = load_config()
    deck = cfg.almanac.lessons.deck
    assert topics_for(1, cfg, 4) == deck[:4]
    assert len(topics_for(1, cfg, 99)) == len(deck)  # never more than the deck


def test_lesson_count_expands_on_thin_day() -> None:
    cfg = load_config()
    base = cfg.almanac.lessons.per_edition
    # a full day stays at the base count
    assert lesson_count_for(cfg, FILL_TARGET_ITEMS) == base
    assert lesson_count_for(cfg, FILL_TARGET_ITEMS + 10) == base
    # a thin day expands, monotonically, capped by HARD_MAX_LESSONS and the deck
    assert lesson_count_for(cfg, 2) > base
    assert lesson_count_for(cfg, 0) == min(HARD_MAX_LESSONS, len(cfg.almanac.lessons.deck))


def test_projected_item_count_caps_by_quota_and_budget() -> None:
    cfg = load_config()
    eng_quota = next(s.max_items for s in cfg.sections if s.id == "eng")
    # a flood of one section is capped by that section's quota, then the budget
    assert projected_item_count(_items("eng", 100), cfg, 24) == min(24, eng_quota)
    assert projected_item_count(_items("eng", 100), cfg, 3) == 3


def test_topics_empty_when_disabled_or_no_deck() -> None:
    cfg = load_config()
    cfg.almanac.lessons.enabled = False
    assert topics_for(1, cfg) == []
    cfg.almanac.lessons.enabled = True
    cfg.almanac.lessons.deck = []
    assert topics_for(1, cfg) == []


def test_brief_known_vs_unknown_topic() -> None:
    cfg = load_config()
    assert "security" in brief_for("cybersecurity", cfg).lower()
    # an unknown key falls back to a humanized version of the raw string
    assert brief_for("medieval_armor", cfg) == "medieval armor"


def test_sports_trivia_brief_names_followed_teams() -> None:
    cfg = load_config()
    followed = [t.name for t in cfg.almanac.teams if t.enabled]
    brief = brief_for("sports_trivia", cfg)
    if followed:
        assert followed[0] in brief
