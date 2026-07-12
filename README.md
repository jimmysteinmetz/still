# still

A finite, calm, printable personal newspaper — one curated edition per day
instead of infinite feeds. Read it once and you're caught up; you will miss
things, and that's the feature.

Full product spec: [`personal-newspaper-spec.md`](personal-newspaper-spec.md)

## Setup

```bash
uv sync
```

The editorial pass uses Gemini via Vertex AI with Application Default
Credentials — no API key. Point it at your GCP project (the gitignored `.env`
is auto-loaded on startup) and log in once:

```bash
cp .env.example .env                    # then set GOOGLE_CLOUD_PROJECT=your-project
gcloud auth application-default login   # once
```

(Gemini on Vertex is served from the `global` endpoint — the code handles that,
and `GOOGLE_CLOUD_LOCATION` overrides it. Set `GEMINI_API_KEY` instead to use
the Developer API.)

The **Upcoming Shows** card (NYC-area concerts for your favorite bands) uses the
SeatGeek API. It's optional — without a key the card just hides. Grab a free
client_id at <https://seatgeek.com/account/develop> and set
`SEATGEEK_CLIENT_ID=...` in the same `.env`.

In production the value lives in **Secret Manager** and is injected as the
`SEATGEEK_CLIENT_ID` env var on the Cloud Run job (`--set-secrets`) — same env
var, no code change, nothing secret on disk or in the repo.

## Usage

Everything is configured by editing [`config/still.yaml`](config/still.yaml) —
add/remove sources, follow teams, tune section quotas, list interests. Then:

```bash
uv run still config check        # validate your edits, see the edition plan
uv run still candidates          # fetch + dedupe + rank, print the candidate pool
uv run still build               # full pipeline → data/editions/<date>.pdf
uv run still build --dry-run     # build without archiving or marking items seen
```

`still build` runs the LLM editorial pass, so it needs the Gemini auth above. To
see the **layout** without that (or without waiting for sports teams to be
in-season), render a sample edition offline:

```bash
uv run scripts/smoke_render.py         # fabricated content + placeholder crests → data/smoke-edition.pdf
uv run scripts/preview_scoreboard.py   # real ESPN crests, populated Scoreboard → data/scoreboard-preview.pdf
open data/scoreboard-preview.pdf
```

WeasyPrint is the primary PDF engine; on a Mac its Homebrew libs are found
automatically (the path is injected into the render subprocess), so no env setup
is needed. Headless Chrome is the fallback if WeasyPrint is missing.

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Tickets

Work is tracked locally with [Backlog.md](https://github.com/MrLesk/Backlog.md)
instead of GitHub Issues — tasks are plain markdown files under `backlog/`,
versioned in this repo.

```bash
backlog task list          # or: backlog board (Kanban view), backlog browser (web UI)
backlog task 3              # view one task
backlog task create "Title" -d "Description" --ac "Acceptance criterion" -l label --priority medium
```

## Status

Working end to end: ingestion (RSS + HN + Reddit) → dedupe (cross-day, by URL
and by topic — a repeat story is skipped even under a different URL or headline)
→ rank → Gemini editorial pass (`gemini-3.5-flash` on Vertex AI) → a dense
**two-page** feature-led broadsheet PDF, archived to `data/editions/`.

The front leads with a **feature well** — the day's marquee story, with a
standfirst and a drop-cap two-column body — beside a rail of two almanac cards:
a **Scoreboard** — last result + next fixture per followed team (or a ≤14-day
season-opener countdown) with monochrome ESPN crests, plus the next IndyCar
race — and **Upcoming Shows**, the next NYC-area concert for each of your bands
(SeatGeek). Below them, **The Margin** — short rotating lessons (cybersecurity,
philosophy, French culture, NYC, sports trivia, vocabulary, world history; the
topic deck rotates daily and expands to fill a thin-news day) — then **The
Wire**: the remaining stories grouped by section. Seven content sections cover
**AI & LLMs, Engineering, Cloud, Sports, Music & Shows, New York, and
Personal**, so the pages fill with things worth reading rather than filler.

The masthead carries a live **weather** ear, a rotating philosopher epigraph,
and **Your Day** — first meeting + meeting count from Google Calendar (optional
OAuth; without a token the line simply omits). The foot closes with a
**Lexicon** — uncommon acronyms/terms from the day's items plus a few French
words — above a one-line condensed Sources footer.

**Next (Phase 2):** email delivery and Cloud Run + Cloud Scheduler.

## License

[MIT](LICENSE)
