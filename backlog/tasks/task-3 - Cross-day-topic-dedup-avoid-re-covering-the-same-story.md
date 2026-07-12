---
id: TASK-3
title: Cross-day topic dedup (avoid re-covering the same story)
status: Done
assignee: []
created_date: '2026-07-09 11:59'
updated_date: '2026-07-11 13:55'
labels:
  - pipeline
  - editorial
dependencies: []
priority: high
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Repeat stories are showing up across consecutive editions (e.g. the same
underlying "Simon Willison SQLite tools" story, 4 days running) because a
different URL each day covers the same real-world topic.

Confirmed root cause: dedup is exact canonical_url match only, unlimited
lookback (db.py:74-76, seen_urls()). A `dedupe_key` (normalized title) is
stored per item (db.py:11-21, idx_items_dedupe) but is NEVER read back
cross-day - it is dead for this purpose; it is only used for same-run title
collisions in pipeline/dedupe.py:12-25. A different URL covering the same
story is invisible to url-based dedup, and exact-title matching would not
reliably catch reworded headlines either.

Recommended direction: pass the LLM a short "recently covered" list (last
~5-7 days of selected headlines/topics, pulled from the editions table) in
build_prompt() and instruct it to skip re-covering the same underlying
story even if the URL/headline differs - semantic topic recognition is a
better fit for the LLM than a mechanical key.

Related but separate finding worth a decision: mark_seen() currently
blacklists the ENTIRE candidate pool each run (cli.py:255, db.py), not just
the items actually selected for the edition - so anything that lost out on
a given day can never resurface, even if it becomes more relevant later.
Confirm whether that is intended before changing it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Editorial prompt includes a recent-topics list from the last several days of selected headlines
- [ ] #2 A story covered under a different URL or headline within the lookback window is not re-selected
- [ ] #3 Decision made (and implemented or explicitly deferred) on whether mark_seen should blacklist only selected items instead of the whole candidate pool
<!-- AC:END -->
