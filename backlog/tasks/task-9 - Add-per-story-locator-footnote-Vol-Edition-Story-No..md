---
id: TASK-9
title: Add per-story locator footnote (Vol / Edition / Story No.)
status: Done
assignee: []
created_date: '2026-07-09 11:59'
updated_date: '2026-07-10 13:48'
labels:
  - render
dependencies: []
priority: low
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add a small locator at the bottom of each story (e.g. "Vol. I - No. 5 -
Story 6") so the reader can find it again later (go back and learn more
about volume 1, edition 5, story 6).

Confirmed: "volume" does not exist as a data concept anywhere - "Vol. I" is
a hardcoded literal (render/templates/edition.html.j2:218).
edition_number is a global monotonic counter (db.py:46-48,
next_edition_number), not reset per volume/year. Each story's sequential
footnote index is already computed as `ref` in render/html.py _row() and
rendered today (edition.html.j2:241 marquee, :312 wire items).

Recommended: no new data model needed - render the locator using the
existing hardcoded volume literal + edition_number + the existing ref
index, e.g. "Vol. I - No. {{ edition_number }} - Story {{ item.ref }}",
placed as small print near each story. Exact placement (under the headline
vs. end of the summary) left to implementation/design taste.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every story (marquee + Wire items) shows a small Vol/Edition/Story-number locator
- [ ] #2 Numbers match what's already used for footnote refs (no new numbering scheme introduced)
- [ ] #3 Locator is unobtrusive (small print) and doesn't visually compete with the headline/summary
<!-- AC:END -->
