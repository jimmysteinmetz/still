---
id: TASK-2
title: Spotify one-off pull to bias Shows + Music news
status: In Progress
assignee: []
created_date: '2026-07-09 11:59'
updated_date: '2026-07-09 12:18'
labels:
  - almanac
  - editorial
dependencies: []
priority: low
ordinal: 500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
One-off pull from the Spotify Web API to inform the Shows card and Music &
Shows news section - the user does not recognize most of the artists/bands
currently surfacing in music news, and wants both music surfaces biased
toward artists they actually listen to.

No Spotify client is installed yet. Personal top-artists/genres needs
user-auth (Authorization Code flow, not Client Credentials), so this needs a
one-time OAuth consent, similar in shape to `still calendar auth`
(src/still/almanac/calendar.py) but this is a ONE-OFF pull, not a recurring
pipeline stage - a small standalone script is fine.

Output feeds two existing places:
- almanac.shows.artists (config.py:141, currently 9 hand-picked artists in
  config/still.yaml:394-403) - the Shows card artist list.
- the `interests` free-text list (config/still.yaml:40-42), read by
  build_prompt() in editorial.py:257,277 - biases which Music & Shows news
  items the LLM selects.

Note: the Shows card is already hard-capped at max_rows=6
(config.py:145, shows.py:42,58), sorted soonest-show-first - that is the
"limit to available space" behavior already in place. The actual lever here
is curating which artists are configured (fewer, better-known-to-the-user
artists), not raising the cap - per the project's principle of never
raising item caps to solve a content problem.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One-off script authenticates to Spotify via user OAuth and prints/exports top artists and genres
- [ ] #2 almanac.shows.artists in config/still.yaml updated to reflect artists the user actually follows
- [ ] #3 interests (or a new structured field feeding build_prompt) updated so music-section selection favors known artists
- [x] #4 No recurring dependency added to the daily pipeline - this is a manual, occasional re-run, not a new pipeline stage
<!-- AC:END -->

## Implementation Notes

Code shipped 2026-07-11: `scripts/spotify_pull.py` (stdlib PKCE Authorization
Code flow + httpx; `SPOTIFY_CLIENT_ID` in `.env`, secret optional; docs in the
module docstring and `.env.example`). Remaining before Done: user creates the
Spotify app, runs `uv run scripts/spotify_pull.py`, and pastes the printed
YAML into `almanac.shows.artists` + `interests` in config/still.yaml (AC #1–3).
