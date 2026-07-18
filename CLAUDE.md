# still — personal newspaper pipeline

A scheduled batch job that builds one finite, printable daily edition from
curated sources. `personal-newspaper-spec.md` is the source of truth for all
product decisions — read the relevant section before changing behavior.

## Commands

```bash
uv sync                      # install
uv run still config check    # validate config/still.yaml, show edition plan
uv run pytest                # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

## Tickets

Work (bugs, feature requests, follow-ups) is tracked locally with
[Backlog.md](https://github.com/MrLesk/Backlog.md), not GitHub Issues — tasks
are markdown files under `backlog/tasks/`, committed to this repo.

```bash
backlog task list                # or: backlog board, backlog browser
backlog task create "Title" -d "Description" --ac "Acceptance criterion" -l label --priority medium
backlog task edit TASK-3 -s "In Progress"
```

Labels used so far: `ingest`, `pipeline`, `editorial`, `render`, `almanac`,
`config`. When filing a ticket, include the confirmed root cause / current
behavior (with file:line references) and a recommended fix direction, not
just a title — future implementation should be able to start straight from
the ticket.

## Architecture

Batch pipeline (spec §7), one stage per module — no services, no real-time:

| Stage | Module | Status |
|---|---|---|
| Ingest | `src/still/ingest/` | rss + hn + reddit done (reddit needs `REDDIT_CLIENT_ID`/`SECRET` in env; its sources skip without them) |
| Normalize/Dedupe/Rank | `src/still/pipeline/` | done (crude rank — editorial does real selection) |
| Editorial (LLM) | `src/still/pipeline/editorial.py` | done — Gemini via Vertex AI + ADC; tiers items (pressing/brief) + writes Margin lessons |
| Almanac | `src/still/almanac/` | weather (Open-Meteo) + sports/Scoreboard (ESPN) + shows (SeatGeek) + Your Day/calendar (Google Calendar OAuth) done |
| Render | `src/still/render/` | done — jinja2 HTML → dense two-page PDF |
| Deliver | email | Phase 2 (PDF + HTML archive to `data/editions/` works) |

CLI: `still candidates` prints the ranked pool (no LLM); `still build` runs
the full chain and writes `data/editions/<date>.pdf` (`--dry-run` skips
archiving/marking seen; `--kind weekend` forces the long-read edition).
SQLite seen-history lives in gitignored `data/`. Adapter tests use
`httpx.MockTransport` — never live network in tests; editorial tests never
call Gemini (budget enforcement is pure code in `enforce_budget`).

## GCP

- **Region: `us-east4` for EVERYTHING** — Cloud Run, Cloud Scheduler, GCS, all
  future infra. Don't introduce other regions. **Sole exception:** Gemini on
  Vertex is called via the `global` endpoint — us-east4 hosts no Gemini publisher
  models (a request there 403s "permission denied / may not exist"). So
  `editorial.DEFAULT_LOCATION = "global"`, not us-east4.
- The GCP project is NOT hardcoded — it comes from `GOOGLE_CLOUD_PROJECT`
  (locally via the gitignored `.env`, auto-loaded at CLI startup; in prod via the
  Cloud Run env).
- Auth is ADC via Vertex AI (see Quirks); no API keys.
- Eventual deploy target: Cloud Run job + Cloud Scheduler, editions archived
  to GCS.

## Quirks

- **PDF engines:** weasyprint (primary) and headless Chrome (fallback) both run
  as timeout-guarded subprocesses in `render/pdf.py`. weasyprint's macOS dylibs
  live in `/opt/homebrew/lib`; `_weasyprint_env` now **injects that onto
  `DYLD_FALLBACK_LIBRARY_PATH` automatically** (only if the dir exists, so Linux/
  Cloud Run is untouched), so `still build` uses weasyprint without exporting
  anything. Chrome is the fallback only if weasyprint is genuinely missing or
  hangs. **The engines paginate differently** — Chrome pins the footer to the
  page bottom (leaving a mid-page gap on a short edition) while weasyprint hugs
  content; always confirm layout on the weasyprint output. Verified via
  `uv run scripts/smoke_render.py` (realistic multi-section content for tuning).
- **weasyprint + multicol:** the edition is a 3-column broadsheet. weasyprint
  infinite-loops if a multicol child has `break-inside: avoid` and is taller
  than a column — keep that only on `.item` (short), never on `.section`. The
  45s subprocess timeout is the backstop if it regresses.
- **Masthead ears + weather icons:** the masthead is one row — weather (left
  ear), nameplate+epigraph, edition meta (right ear) — filling the space that
  flanks the nameplate. Weather icons are tiny inline `stroke="currentColor"`
  SVGs in `render/icons.py`, keyed by weather.fetch's WMO-code buckets; both
  PDF engines render them. Passed to Jinja as `Markup(...)` so autoescape
  doesn't escape the SVG.
- **Masthead epigraph:** under the nameplate, a rotating philosopher quote
  (`render/quotes.py`), chosen by `edition_number % len(QUOTES)` — deterministic,
  changes daily. Replaced the old tagline. To add lines, append `(quote, author)`
  to `QUOTES`; keep them short so they fit under the plate.
- **Feature-led front (the layout):** the edition leads with a **feature well** —
  the single marquee story (big Didot headline, an LLM-written `Selection.deck`
  standfirst, a floated drop-cap 2-column body) beside a right **rail**. Below the
  lead-row sits a full-width **The Margin** band, then **The Wire** — the remaining
  stories in a 4-column multicol, grouped by section with maroon labels. `render_html`
  (`render/html.py`) picks the marquee (first `pressing` selection, else the first
  selection so the well is never empty) and groups the rest into `sections`; footnotes
  number marquee-first, then section by section. `Selection.prominence`
  (`"pressing"`/`"brief"`) only chooses the marquee + lightly emphasizes leftover
  pressing items in The Wire. `kind` swaps the kicker ("The Lead" vs "The Weekend
  Read") and descriptor — the layout itself is identical weekday/weekend. **One maroon
  accent** lives behind the `--accent` CSS var (set it to the ink colour for
  monochrome). Page count is automatic (auto-fit: a thin day is fewer pages, no
  padding); the weasyprint `@bottom-center` folio (`page · pages`) is a nicety Chrome
  omits. Caps stay finite (weekday 24 / weekend 10); density comes from layout + craft,
  never from creeping the budget.
- **The lead-row MUST fit one page (print gotcha — load-bearing):** the feature + rail
  are a `display:flex` row, which is **monolithic in print: flex/grid can't fragment
  across a page break**. If the row grows taller than the space under the masthead,
  weasyprint shoves the *entire* front onto page 2, blanking page 1. So the rail holds
  ONLY the short, bounded cards (**Scoreboard + Shows**) and **The Margin is a separate
  full-width band BELOW the lead-row** (its lessons can number up to 5 and would make a
  narrow rail too tall). Don't move tall/variable content back into the rail. (A
  float-right rail was tried so the front could fragment — weasyprint collapses the
  multicol feature-body beside a float and they *overlap*; flex + a bounded rail is the
  working approach. The marquee length is bounded by the prompt so the well never
  exceeds a page.)
- **Filling two pages (the hard part):** news volume varies, so three levers keep
  the pages full. (1) **Backfill** — the busiest section (eng) has a high quota
  (14) and raised per-source caps (HN 8, Lobsters 5) so it absorbs slack on a
  lopsided day; the prompt says fill ~`max_items` but keep sections balanced,
  leaning on the busy one only when others are thin. (2) **More sources** — extra
  AI/Cloud/Personal feeds (Raschka, The Gradient, Google AI, AWS, Azure, King
  Arthur, Guitar World) richen the thin sections. (3) **Adaptive lessons** — see
  below. Diagnose pool balance with `still candidates` (prints per-section
  `N candidates, quota`); a near-empty page almost always means a thin/lopsided pool.
- **The Margin (rotating lessons):** a full-width band between the lead-row and The
  Wire, rendering its lessons across up to **4 columns** so the card stays short no matter
  the count (up to 5) — see the print gotcha above for why it is NOT in the rail. The
  `.margin-cols` `column-count` is set inline to `min(lesson_count, 4)` so a low-count
  band (e.g. the base 2 lessons on a full day) spans the full page width instead of
  stranding empty columns 3–4; without it the fixed 4-col frame left the band half-blank. Topics
  are a **deck** in `almanac.lessons.deck` (config is the UI; freeform strings);
  `pipeline/lessons.py` `topics_for` rotates them by `edition_number` (same math as
  `quotes.epigraph_for`), `brief_for` maps known keys → a richer LLM brief (unknown
  keys humanize the raw string; `sports_trivia` injects followed teams/series). The
  LLM only *writes* the lessons (`EditorialResult.lessons`, `topic/title/body`); code
  picks the topics and clamps the count in `enforce_budget`. **Count is adaptive:**
  `lesson_count_for` returns the base `per_edition` on a full day but expands (one
  extra per ~4 items short of `FILL_TARGET_ITEMS=18`, capped at `HARD_MAX_LESSONS=5`
  and the deck size) so educational content fills a thin day instead of weak news —
  `build_prompt` requests that many and `enforce_budget` clamps to the same number
  (both via `projected_item_count`). `edition_number` is computed before the editorial
  call in `cli.build` and threaded through `select_and_summarize` → `build_prompt`.
  Keep lessons SHORT — the band lays them out in up to 4 columns with `break-inside:avoid`,
  so 5 lessons stay a couple of lines tall; don't let bodies balloon.
- **Lexicon footer + condensed Sources:** the foot of the page carries a
  **Lexicon** — the editorial LLM returns `glossary` (uncommon acronyms/terms
  pulled from the selected items) and `french_vocab` (a few interesting French
  words), both on `EditorialResult` and both clamped in `enforce_budget`
  (`MAX_GLOSSARY=6`, `MAX_FRENCH=4`) so the model can't pad the page. French rows
  render italic with an `fr.` tag. **Reliability:** Gemini sometimes returns the
  Lexicon empty (it lost the whole footer on 2026-06-27), so `select_and_summarize`
  seeds `french_vocab` from a built-in rotating deck (`render/vocab.py`,
  `edition_number`-rotated like the epigraph) when the model returns none — the foot
  never goes blank. Glossary is content-derived, so an empty one just logs a warning. Below it, **References** are condensed to a
  single run-in line of bare hosts (`render.html.short_ref` strips scheme + path)
  — footnotes are attribution, not tap targets (spec §2.4), so the full URL just
  ate space. The masthead's old "N dispatches · ~M min" line is gone; summaries
  are now denser (2–3 substance-packed sentences) to fill the page with
  information rather than items.
- **Scoreboard / Your Teams (`almanac/sports.py`, ESPN public API, no key):** a
  boxed card at the top of column 1; each row is a monochrome mini-scorebug
  `[you] score [opp] › next-fixture [opp]`. Whether a team shows is derived purely
  from schedule dates — render if the next fixture is ≤14 days out; with a recent
  last result it's in-season (show result+next), else a countdown to the opener.
  Series (IndyCar) read the next race from the league scoreboard. Key facts:
  - One call per team: `…/sports/{espn_path}/teams/{espn_id}/schedule` returns the
    full season with scores, statuses, and a logo URL for **both** teams per game
    (`competitor.team.logos[0].href`) — opponent crest costs nothing extra.
  - Config pins `espn_path` (e.g. `football/nfl`, `basketball/mens-college-basketball`,
    `soccer/eng.1`) + `espn_id`. ESPN's default schedule = the current/upcoming
    season, which is exactly what season-detection wants (off-season teams have no
    near fixture → hidden). **Soccer is the exception** — its default schedule is
    often empty, so we pin `?season=<Aug-start year>`.
  - Series use `…/{espn_path}/scoreboard?dates=<year>` (the bare scoreboard only has
    the current race week; `?dates=` returns the season calendar). Race names get
    `"Grand Prix of "` stripped; the series crest comes from `leagues[0].logos`.
  - ESPN's site API is undocumented (could change); every entity is fetched in its
    own try/except so one failure skips that row, never the card.
- **Upcoming Shows card (`almanac/shows.py`, SeatGeek API):** a boxed card under the
  Scoreboard listing each followed artist's next NYC-metro show (`[artist] · date —
  venue`). Config `almanac.shows` pins the artist list + geo (lat/lng/`range_mi`,
  default NYC); the SeatGeek `client_id` comes from the **`SEATGEEK_CLIENT_ID` env
  var** (free key, not in config — without it the card hides, never blocks a build).
  Locally the var comes from a gitignored `.env` (auto-loaded by `load_dotenv()` at
  CLI startup; `.env.example` is the committed template); in prod it's Secret Manager
  → the Cloud Run env. `load_dotenv` never overrides an already-set var, so the prod
  env always wins.
  One `/2/events` call per artist (`q` + geo + `datetime_utc.gte`, soonest first);
  `_lineup_matches` requires an **exact** performer-name match so a loose `q` hit (a
  tribute act) is rejected. Each artist is fetched in its own try/except (one bad
  lookup skips that row, not the card). Same short-boxed CSS idiom as `.scoreboard`. ESPN logos (500px PNG) are downsized to 96px,
  grayscaled + autocontrasted **in the image bytes** (NOT CSS — WeasyPrint ignores
  CSS `filter`), and inlined as base64 data-URIs so archived editions stay
  self-contained. Cached to gitignored `data/badges/`. A failed logo falls back to
  the team's `short` text label.
- **Your Day (`almanac/calendar.py`, Google Calendar API via OAuth):** a compact
  masthead **right-ear** line (`First mtg 9:30 AM · 5 meetings`, or `No meetings today`)
  showing today's earliest timed event + count. One `events.list` GET with
  `singleEvents=true` (recurrences expanded **server-side** — the whole reason the spec
  pins it) + `orderBy=startTime`; keeps only **timed** events (drops all-day banners) and
  **drops ones you declined** (`attendees[self].responseStatus == "declined"`). Weekdays
  only (`weekdays_only`, default on — the weekend edition has no "first meeting"); config
  `your_day.calendar_id` (default `"primary"`; set it to a work calendar's id — often an
  email — if not primary). Fails graceful like every module: weekend / no token / API
  error → the line just omits, never blocks the build. Key auth facts:
  - **httpx does the API call** (Bearer token) — same idiom as weather/sports/shows and
    keeps mypy-strict clean; `google-auth-oauthlib` is used **only** for the one-time
    `still calendar auth` consent, `google-auth` refreshes the token. No
    `google-api-python-client`.
  - **Secrets via env-var paths** (gitignored `data/`, like `SEATGEEK_CLIENT_ID`):
    `GOOGLE_CALENDAR_CLIENT` (the **downloaded Desktop-app OAuth client JSON** — client_id +
    client_secret; get it from APIs&Services → Credentials → download-icon on your client,
    default `data/google_calendar_client.json`) + `GOOGLE_CALENDAR_TOKEN` (authorized-user
    token the auth command writes, default `data/google_calendar_token.json`). Never read by
    Claude. The client JSON is needed **only** for the one-time `calendar auth`; the resulting
    **token JSON is self-contained** (it embeds token_uri + client_id + client_secret +
    refresh_token), so unattended refresh — and Cloud Run — needs only the **token**, not the
    client file. Prod (later): upload that token JSON to Secret Manager
    (`gcloud secrets create … --data-file=data/google_calendar_token.json`) → Cloud Run env.
    The refresh write-back is **best-effort** (swallows `OSError`) so a read-only secret mount
    can't break the build — only the access token changes on refresh, never the refresh token.
  - **7-day-token gotcha (load-bearing for the unattended job):** an OAuth consent screen
    left in **"Testing"** issues refresh tokens that **expire after 7 days** — publish it to
    **"In production"** (click through the unverified-app warning once) for a non-expiring
    token. And the real feasibility gate is the **work Workspace's third-party app access
    controls** — if the org blocks the app, consent fails outright (pivot: point
    `calendar_id` at a personal calendar, or switch fetch to a secret iCal URL).
  - Scope: `calendar.readonly` (read-only). `fetch` takes an injected access token + httpx
    client so tests use `httpx.MockTransport` — no network, no OAuth in tests
    (`tests/test_calendar.py`).
- **Cross-day topic dedup (`db.py`, `pipeline/dedupe.py`, `pipeline/editorial.py`):**
  two complementary layers, since a mechanical key can't reliably catch a reworded
  headline. (1) `dedupe()` takes an optional `recent_dedupe_keys` set — normalized
  titles (`title_key()`) of items actually selected into editions in the last
  `edition.dedup_lookback_days` (config, default 7) — as a deterministic backstop
  for an identical headline republished under a different URL. (2) `build_prompt()`
  also gets a `recent_topics` list (the raw titles) injected as a "## Recently
  covered" prompt section, so Gemini can skip a genuinely reworded story about the
  same topic — semantic matching is the LLM's job, not a mechanical key. Both come
  from one query, `db.recent_selected_titles(conn, since_date)`, which JOINs
  `items`↔`editions` so only *actually-published* stories count. Load-bearing
  side effect: `mark_seen()` is now called in `cli.build()` with only the
  selected items, not the whole candidate pool — a story that merely lost a
  quota fight one day is no longer blacklisted forever and can resurface later
  if still relevant. (`still candidates --mark-seen` intentionally keeps
  whole-pool semantics — it's a no-LLM preview command with no "selected" set
  to narrow against.)
- The LLM never controls the budget: `editorial.enforce_budget` clamps
  selections to section quotas + edition cap in code. Keep it that way.
- Jinja context uses `entries`, not `items`, for section rows (dict.items
  collision).
- **Gemini auth:** `editorial._make_client()` defaults to Vertex AI + ADC on the
  `global` endpoint. It requires `GOOGLE_CLOUD_PROJECT` (set in the gitignored
  `.env`; `_make_client` raises a clear RuntimeError without it) plus
  `gcloud auth application-default login` once **as a principal with access to
  the project** (ADC ≠ the gcloud CLI credential; a stale/other ADC identity
  403s on `aiplatform.endpoints.predict` even if you're owner via the CLI).
  `GOOGLE_CLOUD_LOCATION` overrides the endpoint;
  `GEMINI_API_KEY` opts into the Developer API. Model: `gemini-3.5-flash`, override via
  `STILL_GEMINI_MODEL`. (Don't go back to a bare `genai.Client()` — it falls through to
  the Developer API and fails with "No API key".) Both client paths carry
  `editorial.RETRY_OPTIONS` (SDK-native `HttpRetryOptions`) so a transient Vertex
  `429` backs off exponentially instead of crashing the build — the pipeline makes
  exactly one editorial call and never retried before; if 429s persist past backoff
  it's a project quota ceiling, not load (raise the Vertex quota).
- The user's safety hook blocks `python script.py` — use `uv run script.py`.

## Principles (non-negotiable, from spec §2)

- **`config/still.yaml` is the user interface.** Sources, sections, interests,
  teams, quotas are all managed by hand-editing it. Config models use
  `extra="forbid"` so typos fail loudly — keep it that way.
- **The finite budget IS the product.** Never raise item caps or add "load
  more" semantics to solve a problem; cut harder instead.
- **Editions are immutable** once final. Archive, never mutate.
- **Sources fail gracefully** — a dead feed skips with a log line, never
  breaks the edition.
- **Calm**: no engagement metrics in output, no notifications, no real-time.

## Conventions

- Python 3.12+, uv exclusively (`uv run`, `uv add`). Type hints everywhere;
  mypy strict.
- Pydantic models for all schemas (`config.py`, `models.py`). New source
  methods = new discriminated-union member in `config.py` + adapter in
  `ingest/`.
- Dependencies are added per-phase, not up front. Installed for rendering:
  `pillow` (crest monochrome processing), `google-auth-oauthlib` (Your Day OAuth consent;
  the Calendar API call itself rides on httpx), `praw` (reddit ingestion). Ask
  before adding others.

## Roadmap position

`still build` runs fetch → editorial (Gemini) → a dense **bold feature-led** PDF.
Masthead has a live Weather ear + a rotating philosopher epigraph (`render/quotes.py`);
the front leads with a **feature well** (the marquee story + its LLM-written deck,
beside a **Scoreboard + Shows** rail), then a full-width **The Margin** band (rotating
LLM-written lessons), then **The Wire** (the rest, grouped by section); the foot closes
with a **Lexicon** (glossary + French vocab) above a one-line condensed Sources footer.
A single maroon `--accent` colours kickers/section labels. Almanac done:
**Weather, Sports, Shows, Lessons, Your Day (Google Calendar)**. Content sections
(spec §4B) are now **AI, Engineering, Cloud, Sports, Music & Shows, New York, Personal**
— the non-tech ones (team blogs, indie-music/show feeds, NYC places/food) were added so
the paper fills two pages with content the reader actually wants, not eng firehose.

**Verified live (2026-06-23):** the full pipeline runs end-to-end on Vertex AI —
`gemini-3.5-flash` (global endpoint) cut 60 candidates to 8 across three sections,
headlined the edition, archived `data/editions/2026-06-23.pdf`. Selection quality
(spec §12, the whole ballgame) reads well; keep an eye on it as sources change.

**Two-page + tiering + Margin lessons:** verified live on 2026-06-24 (prominence +
The Margin both rendered). First live run under-filled page 2 — root cause was a
lopsided pool (eng 49 vs ai 4 / cloud 2 / personal 0) plus a Chrome render (weasyprint
dylib path wasn't set). Fixed: weasyprint env now auto-injected (dense + footer hugs
content); eng backfill quotas; more AI/Cloud/Personal sources; adaptive lesson count.
Pool now projects to the full 24-item budget (`still candidates`: ai 7 / eng 40 /
cloud 3 / personal 6). Re-run `uv run still build` to confirm a full two pages live;
tune `max_items` / section quotas after a few real runs.

**Bold feature-led redesign:** verified live on 2026-06-28 (`still build --kind weekend
--dry-run`, real Gemini, 10 items → 2 full pages). Replaced the old 3-column pressing/
brief broadsheet with the feature-well + bounded-rail + Margin-band + Wire layout, an
auto-fit page count, a maroon `--accent`, the `Selection.deck` standfirst, and a French
fallback deck (`render/vocab.py`) so the Lexicon never empties. The hard bug found and
fixed mid-redesign: a `display:flex` lead-row can't fragment in print, so an over-tall
front blanked page 1 — fixed by bounding the rail (Scoreboard + Shows only) and moving
The Margin to its own full-width band (see the print gotcha in Quirks). Both edition
types tuned offline via the two-volume `scripts/smoke_render.py`. Watch the weekend: a
long marquee + the 10-item cap lands at ~1.5–2 pages — drop the weekend `max_items` if
you want it to settle onto a single dense page.

**Your Day (Google Calendar):** built + verified **offline** on 2026-07-03 — 79 tests green
(incl. `tests/test_calendar.py`: first/last/count, all-day + declined filtered, weekend
short-circuit, HTTP-error → None), mypy/ruff clean, and the masthead line renders in the
weekday smoke PDF (`First mtg 9:30 AM · 5 meetings`; `No meetings today` at count 0; omitted
weekends/when absent). **Not yet verified live** — that needs `still calendar auth` against the
work Workspace account (the real feasibility test of the org's OAuth policy) + the consent
screen published out of "Testing" so the token doesn't expire in 7 days.

**Cross-day topic dedup (TASK-3):** verified offline on 2026-07-11 — 92 tests green
(new `tests/test_db.py` covers `recent_selected_titles`; `test_pipeline.py` /
`test_editorial.py` cover the `dedupe()` title-key backstop and the "Recently
covered" prompt injection), mypy/ruff clean, and `still build --dry-run` ran the
full pipeline including a real Gemini call with no crashes. Also narrowed
`mark_seen` to only the selected items (see the Quirks entry) — fixes a bug where
a quota-dropped candidate could never resurface even if still relevant later.
**Not yet verified live** — the mechanical title-key backstop is deterministic and
test-covered, but confirming Gemini actually skips a *reworded* repeat needs two
consecutive real `still build` days (or manually seeded history).

**Done since:** **Upcoming Shows** activated (SeatGeek `client_id` set). **Your Day**
(`almanac/calendar.py`) built — Google Calendar API via OAuth, first-meeting + count in the
masthead right ear (see the Your Day quirk). Its `still calendar auth` consent + a published
(non-"Testing") OAuth screen is the one live setup step remaining before the unattended job.
**Artist lists refreshed from real listening data (2026-07-18):** the one-off
`scripts/spotify_pull.py` (Spotify top artists, long_term-weighted 4x so multi-year
favorites outrank recent binges) fed both `almanac.shows.artists` (top 25 + 2 hand-picked
keepers) and the music `interests` line (all 27 — the editorial LLM only sees `interests`,
so shows-card artists must be mirrored there by hand). Re-run it every few months;
Spotify's API returns no genre tags for newer apps, so genre wording stays hand-written.

**Immediate next steps (in order):**
1. **Email delivery** then **Cloud Run job + Cloud Scheduler** (region us-east4),
   editions archived to GCS — the rest of Phase 2. (When the job goes live, the Your Day
   token → Secret Manager → the Cloud Run env, like `SEATGEEK_CLIENT_ID`.)

Later: French-holiday + sports-week modules.

To preview the design without the LLM/auth: `uv run scripts/preview_scoreboard.py`
(real ESPN crests) or `uv run scripts/smoke_render.py` (offline placeholders).
