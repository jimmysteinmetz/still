---
id: TASK-1
title: Wire up Reddit ingestion (Phase 3)
status: Done
assignee: []
created_date: '2026-07-09 11:59'
labels:
  - ingest
dependencies: []
priority: medium
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wire up Reddit ingestion (Phase 3). `RedditSource` config already exists
(src/still/config.py) and 3 sources are already configured in
config/still.yaml (LocalLLaMA, ExperiencedDevs, r/guitar), but
src/still/ingest/reddit.py:fetch() is a stub that raises
NotImplementedError("Phase 0 spike"), so all 3 are silently skipped every run.

Scope:
- Implement reddit.py:fetch() using praw.
- Add `praw` to pyproject.toml.
- Add an `isinstance(source, RedditSource)` branch in cli.py _candidate_pool
  (~line 350-358) - currently only Rss/HnAlgolia are handled.
- Handle Reddit API credentials via env vars, same pattern as
  SEATGEEK_CLIENT_ID (cli.py:161) - needs client_id/client_secret/user_agent.

Manual prerequisite (not code): create a Reddit "script" type OAuth app at
reddit.com/prefs/apps to get a client_id/secret.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Configured reddit sources (LocalLLaMA, ExperiencedDevs, r/guitar) appear in still-candidates output
- [x] #2 praw added to pyproject.toml; reddit.py fetch() implemented, no more NotImplementedError
- [x] #3 Reddit credentials read from env vars with the same fail-gracefully pattern as other sources (missing creds skips the source, never breaks the build)
<!-- AC:END -->
