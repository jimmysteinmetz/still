"""Built-in French vocabulary deck — a fallback so the foot-of-page Lexicon never
goes empty when the editorial model declines to return ``french_vocab``.

The live Lexicon is model-written (see ``editorial.LEXICON_BRIEF``), but Gemini
occasionally returns it empty and the template gates the whole block on having
content — so a thin edition loses its footer entirely. This deck rotates by
edition number (same idiom as ``render/quotes.py``) so the words still change
daily when the fallback kicks in. Dependency-free on purpose, like ``quotes``.
"""

# (word, gloss). Glosses kept short — they sit in a 7.5pt multi-column foot.
FRENCH_VOCAB: list[tuple[str, str]] = [
    ("flâner", "to wander the city aimlessly, savoring it for its own sake"),
    ("le quotidien", "the daily — everyday life, or a daily newspaper"),
    ("dépaysement", "the pleasant disorientation of being somewhere unfamiliar"),
    ("l'esprit de l'escalier", "the perfect retort thought of only once the moment has passed"),
    ("terroir", "the soil, climate, and place that give a food or wine its character"),
    ("retrouvailles", "the joy of reuniting with someone after a long time apart"),
    ("râler", "to grumble and complain — a beloved French national pastime"),
    ("bricolage", "tinkering; making do by assembling whatever is at hand"),
    ("la douleur exquise", "the exquisite ache of wanting someone you cannot have"),
    ("chez soi", "the feeling of being at home, at ease in one's own place"),
    ("se débrouiller", "to manage, to figure it out and get by on one's own"),
    ("nous étions", "we were — the warm imperfect of a shared past"),
    ("ailleurs", "elsewhere; the elsewhere one half-longs for"),
    ("savoir-faire", "knowing exactly how — effortless, practiced competence"),
]


def french_fallback(edition_number: int, count: int) -> list[tuple[str, str]]:
    """``count`` (word, gloss) pairs starting at this edition's rotating offset.

    Deterministic and daily-rotating like the masthead epigraph, so successive
    fallbacks don't repeat until the deck is exhausted.
    """
    if count <= 0 or not FRENCH_VOCAB:
        return []
    n = min(count, len(FRENCH_VOCAB))
    start = ((edition_number - 1) * count) % len(FRENCH_VOCAB)
    return [FRENCH_VOCAB[(start + i) % len(FRENCH_VOCAB)] for i in range(n)]
