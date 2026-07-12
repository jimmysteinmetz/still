"""FILTER/RANK stage (spec §7): recency + source class + interest match.

Deliberately crude scoring for the Phase 0 spike — the point is a ranked
candidate pool good enough to judge by eye. The Phase 1 editorial LLM pass
does the real selection; this stage just orders its input sensibly.

Score = recency decay (half-life ~1 day, weight 0.5)
      + trusted-source boost (0.3)
      + interest keyword overlap in title (up to 0.5)
"""

import math
import re
from datetime import UTC, datetime

from still.config import StillConfig
from still.models import Item

STOPWORDS = {
    "a",
    "an",
    "and",
    "in",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
    "not",
    "worth",
    "actually",
    "making",
    "matters",
    "practice",
}


def rank(items: list[Item], config: StillConfig, now: datetime | None = None) -> list[Item]:
    now = now or datetime.now(UTC)
    keywords = _keywords(config.interests)
    for item in items:
        age_hours = max((now - item.published_at).total_seconds() / 3600, 0.0)
        recency = math.exp(-age_hours / 24)
        trusted = 0.3 if item.class_ == "trusted" else 0.0
        matches = len(_tokens(item.title) & keywords)
        interest = min(matches, 3) / 3 * 0.5
        item.score = round(0.5 * recency + trusted + interest, 3)
    return sorted(items, key=lambda i: i.score or 0.0, reverse=True)


def _keywords(interests: list[str]) -> set[str]:
    return {token for phrase in interests for token in _tokens(phrase)} - STOPWORDS


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+]+", text.lower()))
