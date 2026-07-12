---
id: TASK-5
title: 'Fix pagination: thin trailing page (1-2 stories + Lexicon)'
status: Done
assignee: []
created_date: '2026-07-09 11:59'
labels:
  - render
  - editorial
dependencies: []
priority: medium
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Some editions force an extra page that ends up with only 1-2 stories plus
the Lexicon - wasted, sparse final page.

Two confirmed contributing causes:
(a) enforce_budget (editorial.py:322-323) recomputes the adaptive lesson
count from the CANDIDATE POOL (via projected_item_count), not the LLM's
actual final selection count - so the adaptive-fill logic in
pipeline/lessons.py never reacts to a conservative real selection. A rich
pool with a conservative LLM pick still gets the base lesson count instead
of an expanded one, leaving nothing to fill the thin page.
(b) .wire and .lex-cols use a fixed column-count: 4
(render/templates/edition.html.j2:160, 177) regardless of item count,
unlike .margin-cols which already computes min(count,4) inline
(edition.html.j2:297) - a thin final page can strand a couple of items
across 4 narrow columns instead of collapsing to fewer, wider ones.

Recommended: apply the same adaptive column-count treatment to
.wire/.lex-cols, and consider re-clamping lesson count against the real
selection count after the LLM responds rather than only the pre-hoc pool
estimate. Removing the Sources/References footer (separate ticket) also
removes one more thing that could tip a thin page over into a new one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A thin edition (few Wire items) no longer spills a near-empty extra page
- [x] #2 .wire and .lex-cols column-count adapts to actual item count like .margin-cols already does
- [x] #3 Lesson count reflects (or is re-clamped against) the LLM's actual selection count, not just the pool estimate
- [x] #4 Verified visually via tests/smoke_render.py with a deliberately thin item count
<!-- AC:END -->
