"""French vocabulary fallback deck rotation."""

from still.render.vocab import FRENCH_VOCAB, french_fallback


def test_consecutive_editions_share_no_words() -> None:
    for edition in range(1, 50):
        words_now = {w for w, _ in french_fallback(edition, 3)}
        words_next = {w for w, _ in french_fallback(edition + 1, 3)}
        assert not words_now & words_next, f"editions {edition} & {edition + 1} share words"


def test_full_deck_cycles_over_time() -> None:
    all_words = set()
    for edition in range(1, len(FRENCH_VOCAB) * 3 + 1):
        all_words.update(w for w, _ in french_fallback(edition, 3))
    all_deck_words = {w for w, _ in FRENCH_VOCAB}
    assert all_words == all_deck_words


def test_every_entry_has_word_and_gloss() -> None:
    for word, gloss in FRENCH_VOCAB:
        assert word.strip()
        assert gloss.strip()


def test_avoid_filters_out_given_words() -> None:
    avoid = {FRENCH_VOCAB[0][0], FRENCH_VOCAB[1][0]}
    picked = french_fallback(1, 3, avoid=avoid)
    assert not {w for w, _ in picked} & avoid
    assert len(picked) == 3


def test_avoid_none_or_empty_matches_default_behavior() -> None:
    assert french_fallback(5, 3, avoid=None) == french_fallback(5, 3)
    assert french_fallback(5, 3, avoid=set()) == french_fallback(5, 3)


def test_avoid_covering_whole_deck_still_returns_count() -> None:
    avoid = {w for w, _ in FRENCH_VOCAB}
    picked = french_fallback(1, 3, avoid=avoid)
    assert len(picked) == 3
