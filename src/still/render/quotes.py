"""Masthead epigraph — a rotating philosopher's line under the nameplate.

Replaces a throwaway tagline with one short, well-attributed quote, chosen
deterministically by edition number so it changes daily and never repeats until the
list is exhausted. Leans toward attention, finitude, and calm — the paper's temper.
"""

# (quote, author). Kept short enough to sit under the nameplate.
QUOTES: list[tuple[str, str]] = [
    ("The unexamined life is not worth living.", "Socrates"),
    ("Knowing yourself is the beginning of all wisdom.", "Aristotle"),
    ("Confine yourself to the present.", "Marcus Aurelius"),
    ("Very little is needed to make a happy life.", "Marcus Aurelius"),
    ("We suffer more often in imagination than in reality.", "Seneca"),
    ("It is not that we have a short time to live, but that we waste much of it.", "Seneca"),
    ("Wealth consists not in having great possessions, but in having few wants.", "Epictetus"),
    ("It is not what happens to you, but how you react, that matters.", "Epictetus"),
    ("No man ever steps in the same river twice.", "Heraclitus"),
    ("All our problems stem from our inability to sit quietly in a room alone.", "Pascal"),
    ("A wise man proportions his belief to the evidence.", "David Hume"),
    ("Beauty is no quality in things; it exists in the mind that contemplates them.", "David Hume"),
    ("Science is organized knowledge. Wisdom is organized life.", "Immanuel Kant"),
    ("He who has a why to live can bear almost any how.", "Friedrich Nietzsche"),
    ("You must have chaos within you to give birth to a dancing star.", "Friedrich Nietzsche"),
    ("In the depth of winter, I found within me an invincible summer.", "Albert Camus"),
    ("Real generosity toward the future means giving all to the present.", "Albert Camus"),
]


def epigraph_for(edition_number: int) -> tuple[str, str]:
    """Pick a (quote, author) for this edition — deterministic, rotates daily."""
    return QUOTES[(edition_number - 1) % len(QUOTES)]
