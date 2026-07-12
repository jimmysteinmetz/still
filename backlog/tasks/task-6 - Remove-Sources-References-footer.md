---
id: TASK-6
title: Remove Sources/References footer
status: Done
assignee: []
created_date: '2026-07-09 11:59'
updated_date: '2026-07-10 13:48'
labels:
  - render
dependencies: []
priority: low
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Remove the condensed Sources/References footer entirely - footnote numbers
already give a way back to attribution, and the bare-host line at the foot
of the page just eats space (also a contributor to the thin-trailing-page
pagination issue).

Delete:
- render/templates/edition.html.j2:334-338 (markup) and :183-188 (CSS)
- the references= kwarg in render/html.py:98
- short_ref() in render/html.py:111-118 (confirmed unused elsewhere once
  this is removed)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 References section no longer renders in the PDF
- [ ] #2 short_ref() and the references= plumbing removed from html.py
- [ ] #3 uv run pytest and mypy stay clean
<!-- AC:END -->
