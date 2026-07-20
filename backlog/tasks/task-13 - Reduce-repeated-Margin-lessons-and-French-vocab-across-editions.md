---
id: TASK-13
title: Reduce repeated Margin lessons and French vocab across editions
status: Done
assignee: []
created_date: '2026-07-19 17:43'
updated_date: '2026-07-19 17:51'
labels:
  - almanac
dependencies: []
priority: medium
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Root cause: Margin lesson content (pipeline/lessons.py) and Lexicon french_vocab (render/vocab.py, pipeline/editorial.py:264-269) have zero cross-day dedup, unlike news items which already get this via db.recent_selected_titles -> RECENT_TOPICS_BRIEF (see CLAUDE.md 'Cross-day topic dedup'). Margin lessons: topics_for() rotates topic *category* keys deterministically (7-item deck, per_edition=2, step 1 -> consecutive editions always share a category), but the LLM-written lesson *body* per category has no history/anti-repeat mechanism at all. French vocab: LEXICON_BRIEF only says 'vary them day to day' with zero enforcement; the code-level fallback deck (render/vocab.py french_fallback) only triggers when Gemini returns french_vocab empty, and even then has no memory of previously-shown words across editions. Fix: extend the existing recent_selected_titles/RECENT_TOPICS_BRIEF pattern to lessons and vocab -- new db.py tables (lessons, french_vocab) + recent_lessons()/recent_french_words()/save_lessons_and_vocab(), prompt injection (RECENT_LESSONS_BRIEF, LEXICON_BRIEF avoid_french slot) in pipeline/editorial.py, plus a hard code-level backstop for vocab specifically (_finalize_french_vocab, since French words are short literal strings and the prompt-only instruction has already proven unreliable for this field) since lesson prose has no cheap way to mechanically detect semantic repeats. topics_for's category-rotation math is left unchanged; content-level dedup should be enough on its own.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Margin lesson content does not repeat within the dedup_lookback_days window
- [ ] #2 French vocab words do not repeat within the dedup_lookback_days window, enforced in code not just prompt
- [ ] #3 New DB tables/functions covered by tests; existing vocab.py rotation tests unmodified/passing
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: db.py (lessons/french_vocab tables + recent_lessons/recent_french_words/save_lessons_and_vocab), vocab.py (avoid-aware french_fallback with top-up), editorial.py (RECENT_LESSONS_BRIEF prompt injection nested under 'if topics', LEXICON_BRIEF avoid_french slot, _finalize_french_vocab hard backstop run after enforce_budget), cli.py (wires recent_lessons/recent_french history in, persists after save_edition). 21 new tests across test_db.py/test_vocab.py/test_editorial.py, all passing; ruff+mypy clean on touched files; verified end-to-end with a real 'still build --dry-run' (Lexicon rendered correctly). Note: a concurrent session was mid-refactor on the fixed two-page layout (pipeline/layout.py) during implementation -- merged cleanly, no conflicts in the touched files.
<!-- SECTION:NOTES:END -->
