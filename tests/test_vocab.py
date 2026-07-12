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
