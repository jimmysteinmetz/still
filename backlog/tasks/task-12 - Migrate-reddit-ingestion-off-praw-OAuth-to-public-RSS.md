---
id: TASK-12
title: Migrate reddit ingestion off praw/OAuth to public RSS
status: Done
assignee: []
created_date: '2026-07-19 17:14'
updated_date: '2026-07-19 17:15'
labels:
  - ingest
dependencies: []
priority: medium
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reddit closed self-service OAuth app registration in late 2025 under its Responsible Builder Policy — clicking 'create app' at reddit.com/prefs/apps no longer creates an app, it bounces to the policy article; new API access now needs a manual approval ticket. This broke the praw-based reddit.py adapter's only viable credential path (REDDIT_CLIENT_ID/SECRET could never be obtained). Fix: rewrote src/still/ingest/reddit.py to fetch each subreddit's public https://www.reddit.com/r/{sub}/top/.rss?t=day feed over the shared httpx.Client (same pattern as rss.py/hn.py) — no OAuth, no credentials, no approval needed. The feed carries no upvote score, so RedditSource.min_upvotes was dropped from config.py and config/still.yaml (the /top/.rss ordering + max_items cap stand in for it). Dropped the praw/prawcore dependency and the REDDIT_CLIENT_ID/SECRET/USER_AGENT env vars (.env.example updated). Link vs self-post detection parses the feed's fixed [link]/[comments] anchor spans via regex (verified against a live LocalLLaMA fetch); self-text is pulled from the SC_OFF/SC_ON div and HTML-unescaped for the editorial excerpt.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 reddit.py fetches via public RSS, no praw/OAuth/credentials required
- [x] #2 RedditSource.min_upvotes removed from config.py + still.yaml (three sources: LocalLLaMA, ExperiencedDevs, guitar)
- [x] #3 tests/test_reddit.py rewritten against mocked RSS (httpx.MockTransport), all green; mypy/ruff clean
- [x] #4 Verified live via 'still candidates' — r/LocalLLaMA returned real items with no credentials set
<!-- AC:END -->
