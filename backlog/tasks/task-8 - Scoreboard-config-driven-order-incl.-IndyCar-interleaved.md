---
id: TASK-8
title: 'Scoreboard: config-driven order incl. IndyCar interleaved'
status: Done
assignee: []
created_date: '2026-07-09 11:59'
updated_date: '2026-07-11 14:40'
labels:
  - almanac
  - config
dependencies: []
priority: medium
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reorder the Scoreboard to: Indiana Basketball, Colts, IndyCar, Indiana
Football, Pacers, Tottenham, 49ers.

Confirmed sports.py:54-84 already renders teams in exact config list order
with NO re-sort - so reordering config/still.yaml:327-357 teams list
alone handles most of this. The blocker: series (IndyCar) are always
appended AFTER all teams (sports.py:74-83), never interleaved - but the
desired order needs IndyCar third, between Colts and Indiana Football.

Scope:
- Reorder almanac.teams in config/still.yaml (config-only change).
- Code change: unify teams + series into one ordered rendering list (e.g.
  a single config sequence, or a shared order field) instead of the
  current teams-then-series concatenation, so IndyCar can land between two
  teams.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Scoreboard renders: Indiana Basketball, Colts, IndyCar, Indiana Football, Pacers, Tottenham, 49ers
- [x] #2 Teams and series share one ordered list (no more fixed teams-then-series concatenation)
- [x] #3 Off-season teams still collapse out of the list as they do today
<!-- AC:END -->
