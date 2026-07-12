---
id: TASK-4
title: Fix repeating French vocab fallback words
status: Done
assignee: []
created_date: '2026-07-09 11:59'
updated_date: '2026-07-10 13:48'
labels:
  - render
dependencies: []
priority: low
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
French vocab phrases in the Lexicon footer are repeating within about a
week.

Confirmed root cause: render/vocab.py FRENCH_VOCAB fallback deck has 14
entries (lines 12-27). The rotation window (lines 30-40) advances by only 1
edition per call but takes 3 words, so consecutive fallback-triggering
editions share 2 of 3 words verbatim (day N picks [s,s+1,s+2], day N+1 picks
[s+1,s+2,s+3]) - individual words repeat on the very next fallback
occurrence rather than needing the full 14-edition cycle. Compare
render/quotes.py epigraph_for, which picks a single non-overlapping index
and does not have this problem.

Fix: make the window non-overlapping, e.g.
start = ((edition_number - 1) * count) % len(deck)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Consecutive fallback-triggering editions share zero words (non-overlapping window)
- [ ] #2 Full deck still cycles through all 14 entries over time
- [ ] #3 tests/test_vocab.py (or equivalent) covers the non-overlap property
<!-- AC:END -->
