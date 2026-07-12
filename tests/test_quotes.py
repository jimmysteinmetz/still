"""Masthead epigraph rotation."""

from still.render.quotes import QUOTES, epigraph_for


def test_rotation_is_deterministic_and_cycles() -> None:
    assert epigraph_for(1) == QUOTES[0]
    assert epigraph_for(2) == QUOTES[1]
    assert epigraph_for(2) != epigraph_for(1)
    assert epigraph_for(len(QUOTES) + 1) == QUOTES[0]  # wraps around


def test_every_quote_is_attributed() -> None:
    for quote, author in QUOTES:
        assert quote.strip()
        assert author.strip()
