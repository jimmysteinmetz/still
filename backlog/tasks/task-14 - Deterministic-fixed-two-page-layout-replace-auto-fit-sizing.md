---
id: TASK-14
title: Deterministic fixed two-page layout (replace auto-fit sizing)
status: Done
assignee: []
created_date: '2026-07-19 18:20'
updated_date: '2026-07-19 18:20'
labels:
  - editorial
dependencies: []
priority: high
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Live editions kept mis-sizing under the auto-fit layout: 2026-07-19 ran to 3 pages (half-empty Wire on p1, Lexicon stranded on a near-blank p3); 2026-07-18 stranded the Wire band label over dead space on p1. Root cause: the template had zero fixed heights (page count emergent from content flow) and word counts were prompt-advisory only — enforce_budget clamped counts, never text length.

Fix (implemented): fixed two-page geometry. New src/still/pipeline/layout.py is the single contract — P1_WIRE_SLOTS=4, P2_WIRE_SLOTS (weekday 13 / weekend 5), WORD_CAPS per kind/tier, capacity() (18/10), split_wire() shared by enforce_budget and render_html. clamp_to_layout() truncates every text field at a sentence boundary; prompts retargeted (exactly 5 pressing: marquee 150-190w + 4 front-row 70-90w). Template: two fixed 260mm .sheet blocks; p1 = masthead + fixed-height lead-row + abspos bottom-anchored 4-story Wire front row (.wire-front); p2 = everything in abspos .p2-inner — Margin at top, Wire continued, Lexicon pinned to the foot. still.yaml weekday max_items 24->18.

Load-bearing weasyprint findings (in CLAUDE.md Quirks): overflow:hidden does NOT stop an over-full in-flow block from spilling extra pages (fragmentation precedes paint clipping); column-flex doesn't help and flex ignores max-height; only abspos content never fragments — hence the abspos wells. Verified: smoke_render fixtures all pages=2 (script exits 1 otherwise), pypdf locator check shows zero clipped stories, and a 70x over-cap bloat fixture still renders exactly 2 pages. Not yet verified live (needs a real still build).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All three smoke_render fixtures render exactly 2 pages on WeasyPrint
- [ ] #2 Word caps enforced in code, not just prompted
- [ ] #3 Overlong content degrades to clipped text, never a third page
<!-- AC:END -->
