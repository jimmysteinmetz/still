# Personal Newspaper — Product Specification

*Working title: "The Daily" (naming open). A finite, calm, printable daily edition that replaces infinite scrolling with a single, bounded artifact you read once and are done.*

*Status: living draft. This version supersedes all earlier drafts and integrates the expanded source list, the newsletter ingest inbox, and the front-page "almanac" modules.*

---

## 1. Vision & intent

The product exists to solve a specific attention problem: infinite, novelty-driven feeds (Twitter/X especially) fragment attention and pull you back repeatedly through the day. This app replaces that with the opposite shape — **one finite edition per day**, curated and summarized, ideally **read on paper** so consumption happens away from a screen and away from the tap-to-open loops.

The core contract with the reader: *"Read this once and you are caught up. You will miss things, and that is the feature."*

It is not a feed reader, not a real-time dashboard, not a social client. It is a newspaper: it has an edition, a front page, a finite page count, and an end.

---

## 2. Design tenets (non-negotiable)

1. **Finite.** Every edition has a hard ceiling — a fixed maximum item count and/or page count. When the budget is spent, the edition is done. No "load more."
2. **Batched.** Generated on a schedule (default: once daily, early morning). No live updates, no notifications, no real-time anything.
3. **Calm.** No engagement metrics surfaced (no like/retweet counts as bait), no rage-optimized ranking, no infinite tail. Ranking optimizes for signal and your stated interests, not for "engagement."
4. **Printable / screen-optional.** The canonical output is a print-ready PDF (and/or e-ink later). Consumption should be possible entirely off-device. Links are present but as footnotes/QR, never as taps that pull you into an app.
5. **Deliberately under-complete.** FOMO is the enemy. The editorial job is to *cut*, not to be comprehensive. Better to surface 12 great things than 60 adequate ones.
6. **Single source of truth = the edition.** Once generated, an edition is immutable and archived. You can always reprint it; it never changes under you.

---

## 3. Target user (you)

A data engineer / technology director, heavy prior Twitter user actively trying to reduce phone/feed dependence, strong in Python and React/Next.js, comfortable with GCP and LLM pipelines (you already run a Gemini-based extraction pipeline for tasks). You want a daily artifact that keeps you informed on AI/engineering and a few personal interests **without** reopening the scroll, plus a practical "start of day" briefing.

---

## 4. The edition: anatomy

### 4.0 Cadence & editions (decided)

Two recurring editions, sharing one pipeline and differing only in editorial budget/prompt and layout template:

- **Weekday Daily (Mon–Fri):** the standard finite edition described below — Almanac + curated quick-hit sections, read in one short sitting before the day starts.
- **Weekend Feature (one edition, Sat or Sun):** a *different* edition, **not a lighter one**. It leads with **one developed long-read** — a single marquee story given real space (deeper summary or full text, context, why-it-matters) — backed by only a small handful of supporting items. The editorial job shifts from "select ~12 quick hits" to "pick the one story most worth your weekend attention and develop it." The Almanac runs in relaxed form (no "first meeting"; lean on weather, upcoming French holidays, and the fuller weekend sports slate). Designed for the fact that you have more time and want depth, not breadth.

A daily edition has two halves:

**A. The Almanac (front page / masthead).** Short, factual, personal. This is the "start my day" briefing.
**B. The Sections (content).** Curated, ranked, summarized items from your sources, grouped into a few named sections.

### 4A. Almanac modules

| Module | What it shows | Data source | Notes |
|---|---|---|---|
| **Masthead** | Date, edition #, estimated read time, item count | Generated | Read-time = sum of per-item estimates; reinforces "finite." |
| **Your Day** | First meeting of the day, total meetings, first/last times | Google Calendar API | Weekdays only (per your spec). Skip/condense on weekends. |
| **Weather** | Today's high/low, conditions, precip; optional tomorrow | Open-Meteo (no key) | Home lat/long configurable. |
| **Upcoming French holidays** | Any major FR public holiday in the next ~2–4 weeks | Nager.Date (`/PublicHolidays/{year}/FR`) | Relevant if you follow French holidays. Only render when something is upcoming. |
| **This Week in Sports** | Notable fixtures in the next 7 days across your leagues | TheSportsDB | Filtered to your leagues; cap at a few items. |
| **Your Teams** | Last result + next fixture for each followed team | TheSportsDB | Teams: Tottenham (EPL), 49ers (NFL), Colts (NFL), Indiana Hoosiers (NCAA FB/MBB). |

Almanac design rule: each module is **conditionally rendered** — if there's nothing notable (no upcoming holiday, off-season for a team), it collapses or disappears rather than printing filler.

### 4B. Content sections (default grouping)

- **AI & LLMs** — the core beat.
- **Engineering & Tech** — broader software/eng.
- **Cloud / GCP** — your work-relevant subset.
- **Personal** — cooking, guitar, and any non-sports interests (sports live in the Almanac).

Each section has its own item quota so no single firehose dominates.

---

## 5. Sources

Sources are **source-agnostic at ingestion** and classified two ways that drive how hard the editorial filter works:

- **Class:**
  - **Trusted / low-frequency** (individual blogs, weekly newsletters): pass through near-verbatim; light summarization only.
  - **Firehose** (HN, arXiv, Lobsters, Reddit): hard pre-filters (points/recency/keyword) **then** an LLM editorial pass that keeps only what matches your interests.
- **Quota:** each source (and each section) has a max items/edition so the finite budget is shared fairly.

### 5.1 Ingestion methods (taxonomy)

1. **Native RSS/Atom** — preferred, cheapest, most stable.
2. **JSON/Atom API** — HN, arXiv, GitHub releases, sports/weather/holidays.
3. **Email newsletter → ingest inbox** — for newsletter-only/paid sources (see §5.5).
4. **X/Twitter** — special case (see §5.6).
5. **Scrape** — last resort, brittle; only for high-value sites with no feed.

### 5.2 AI / LLM sources

| Source | Feed / endpoint | Method | Class |
|---|---|---|---|
| Simon Willison | `https://simonwillison.net/atom/everything/` (or `/atom/entries/` for long-form only; per-tag via `…/tags/llms.atom`) | RSS | Trusted |
| Import AI (Jack Clark) | `https://jack-clark.net/feed/` | RSS | Trusted |
| Latent Space (swyx) | `https://www.latent.space/feed` | RSS (or email) | Trusted |
| The Batch (DeepLearning.AI) | site RSS | RSS | Trusted |
| Hugging Face blog | `https://huggingface.co/blog/feed.xml` | RSS | Semi-trusted |
| Vendor blogs (Anthropic / OpenAI / Google AI) | per-site RSS where available | RSS | Trusted, low-freq |
| arXiv `cs.LG` / `cs.AI` / `cs.CL` | `http://export.arxiv.org/rss/cs.LG` (etc.) | RSS/API | **Firehose** — heavy filter |

*arXiv note:* far too high-volume to pass through. Pre-filter to your keyword interests, then let the LLM keep only a handful genuinely worth your attention. Consider capping at 2–3 papers/edition.

### 5.3 Engineering / Tech sources

| Source | Feed / endpoint | Method | Class |
|---|---|---|---|
| Hacker News | Algolia: `http://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=created_at_i>{since},points>{threshold}` | JSON API | **Firehose** — points+recency filter, then LLM editorial |
| Lobsters | `https://lobste.rs/rss` (or tag feeds `…/t/ai.rss`) | RSS | Firehose-lite |
| Reddit (curated subs) | OAuth free tier via `PRAW`; `…/r/{sub}/top.json?t=day` or `…/r/{sub}/top/.rss?t=day` | JSON API / RSS | **Firehose** — top-of-day + upvote threshold, then LLM cut; dedupe vs HN |
| The Pragmatic Engineer (Gergely Orosz) | Substack (mostly paid) | Email ingest | Trusted |
| Google Cloud blog | site RSS (confirm current path at build) | RSS | Semi-trusted (GCP-relevant) |
| GitHub releases (tracked repos) | `https://github.com/{org}/{repo}/releases.atom` | Atom | Trusted, targeted |
| Individual eng blogs (e.g., Julia Evans `https://jvns.ca/atom.xml`) | per-site RSS | RSS | Trusted |

*HN recipe:* the Algolia `search_by_date` endpoint with `created_at_i > now-24h` and `points > N` (start N≈100, tune) gives you "best of the last day above a quality bar" in a single call — the cleanest finite-digest primitive. The Firebase API (`/v0/beststories.json` → `/v0/item/{id}.json`) is the alternative if you want HN's own "best" ranking instead of a points cutoff.

*Reddit recipe:* Reddit's free tier (OAuth, ~100 req/min, non-commercial — fine for a personal tool) is ample here: one `top?t=day` call per subreddit pulls the day's best in a single request. Use **PRAW** (handles auth, rate limits, pagination) in the Python v1, and identify your bot with a descriptive User-Agent. Curate a small set of high-signal subs and apply an upvote threshold; because Reddit and HN surface many of the same links, the **dedupe stage matters**. Public `…/top/.rss?t=day` feeds also work without OAuth at very low volume.

### 5.4 Personal-interest sources

- **Sports** → handled in the Almanac via TheSportsDB (see §4A and §6). No raw sports feeds in the content sections.
- **Cooking** → RSS where available (e.g., Serious Eats, Smitten Kitchen) and/or r/cooking top-of-day; trusted + firehose.
- **Guitar / vintage gear** → RSS where available, an ingest-inbox newsletter, or r/guitar top-of-day (filtered). Low-priority quota.
- **Tech/AI subs** (r/LocalLLaMA, r/MachineLearning, r/programming, r/ExperiencedDevs) feed the AI/Eng sections, not Personal — see §5.3.

### 5.5 Newsletter ingest inbox (you opted in)

Set up a **dedicated inbox** (e.g., a Gmail/Fastmail address or alias) used only for newsletter subscriptions. Two implementation options:

- **Option A — "Kill the Newsletter"-style email→RSS bridge:** each subscription gets a unique address that converts incoming emails into an Atom feed, which your pipeline reads like any other RSS source. Lowest-code; keeps everything uniform as feeds.
- **Option B — Direct IMAP/Gmail-API ingest:** poll the inbox, parse each newsletter's HTML (Substack/Beehiiv/Mailchimp have consistent structures), extract title + body + canonical link, map sender→source. More control, more parsing work.

Recommendation: **start with Option A** for speed and uniformity; move specific high-value newsletters to Option B only if their email formatting needs custom extraction. Each newsletter is registered as a source with its own class/quota like any feed.

### 5.6 X / Twitter — out of scope (decided), and the propagation rationale

**Decision: X/Twitter is dropped from the product, not merely deferred.** It is the single hardest and most expensive integration, and — given the once-daily, calm cadence — it adds almost nothing the other sources don't already deliver.

*Why the cost was prohibitive:* as of the February 2026 change, new developers can't sign up for the old $200 Basic / $5,000 Pro tiers; X moved to pay-per-use ($0.005/read, free tier write-only at ~100 reads/month), and third-party scrapers are cheaper but carry ToS/reliability risk.

*Why dropping it loses little (the propagation thesis):* for tech/AI/engineering, anything that genuinely matters reliably surfaces on Hacker News, Reddit, Lobsters, and the blogs/newsletters within hours — well inside a once-a-day cadence. The Twitter-first-fifteen-minutes advantage is exactly the real-time velocity this product deliberately rejects. What you'd actually lose is specific individuals' live threads — and the fix is to follow *those people directly* via their blogs/newsletters/RSS (Willison, Import AI, etc.), which the source list already does.

*Containment note:* Reddit is itself an infinite-scroll engagement machine. Consuming it **only through the digest** (top-of-day, filtered, printed) is the same containment trick that made this product attractive as a Twitter replacement — you harvest the signal without exposing yourself to the scroll. Never open Reddit; let the edition harvest it.

---

## 6. Almanac data sources (APIs)

| Need | API | Auth | Notes |
|---|---|---|---|
| First meeting / your day | **Google Calendar API** (`events.list`, `timeMin`=today 00:00, `singleEvents=true`, `orderBy=startTime`) | OAuth (you're already connected) | Take earliest timed event as "first meeting"; count events; weekdays only. |
| Weather | **Open-Meteo** (`/v1/forecast?latitude=…&longitude=…&daily=…`) | None | Free, no key, global. Configured home coords. NWS `api.weather.gov` is a US-only alternative. |
| French public holidays | **Nager.Date** (`/api/v3/PublicHolidays/{year}/FR`) | None | Filter to next ~2–4 weeks; render only when something's upcoming. |
| Sports — fixtures & results | **TheSportsDB** (`eventsnext.php`, `eventslast.php`, `eventsday.php`, league lookups; EPL league id 4328) | Free test key | Covers EPL, NFL, NCAA. Primary choice for a personal tool. |
| Sports — fallback / richer detail | **API-Sports / API-Football** | Free tier (~100 req/day) | Use if TheSportsDB lacks an NFL/NCAA detail you want. |

**Followed teams (config):** Tottenham Hotspur (EPL), San Francisco 49ers (NFL), Indianapolis Colts (NFL), Indiana Hoosiers (NCAA football + men's basketball). For each: last result + next fixture in the Almanac; off-season teams collapse automatically.

---

## 7. System architecture

A scheduled batch pipeline (a cron-style job), not a service:

```
                ┌────────────┐
   sources ───▶ │  INGEST    │  fetch RSS/API/email; per-source adapters
                └─────┬──────┘
                      ▼
                ┌────────────┐
                │ NORMALIZE  │  → common Item schema (title, url, source, ts, body, class)
                └─────┬──────┘
                      ▼
                ┌────────────┐
                │  DEDUPE    │  cross-source URL/title-similarity dedupe
                └─────┬──────┘
                      ▼
                ┌────────────┐
                │ FILTER/RANK│  recency + per-source thresholds + interest match
                └─────┬──────┘
                      ▼
                ┌────────────┐
                │  EDITORIAL │  LLM pass: select within budget, summarize, section, headline
                └─────┬──────┘
                      ▼
                ┌────────────┐
                │  ALMANAC   │  fetch calendar/weather/holidays/sports
                └─────┬──────┘
                      ▼
                ┌────────────┐
                │  RENDER    │  HTML + print CSS → PDF (newspaper layout)
                └─────┬──────┘
                      ▼
                ┌────────────┐
                │  DELIVER   │  email PDF / save to drive / auto-print; archive edition
                └────────────┘
```

The **editorial LLM pass** is the heart of the product and the main place to invest. It receives the filtered candidate pool plus your interest profile and the edition budget, and it: selects within the item cap, writes 1–3 sentence summaries, assigns sections, and writes section/edition headlines. This is exactly the Gemini-pipeline shape you already run for task extraction — reuse that pattern.

---

## 8. Tech stack & the Rust question

**Recommendation: build v1 in Python; learn Rust by rewriting one carved-out component.**

This workload is I/O-bound glue plus an LLM call: fetch many sources, parse, rank, summarize, render. That is precisely where Rust's strengths (memory safety, raw perf, fearless concurrency) buy little, and its costs (borrow-checker friction, async/`tokio` ceremony, thinner LLM-SDK ecosystem) hit hardest — right in the v0 loop where you most need fast iteration to tune the *editorial* logic, which is the real product risk. Glue/API projects are also one of the *weaker* ways to learn Rust; you'd fight `serde` and async instead of learning ownership.

**Plan that serves both goals:**

1. **Ship v1 in Python.** Reuse your Gemini pipeline pattern. Suggested libs: `feedparser` (RSS/Atom), `httpx` (async fetch), `pydantic` (the Item schema), an LLM SDK (Gemini or Anthropic), `jinja2` + `weasyprint` or headless Chromium (HTML→PDF), `apscheduler`/cron or a GCP Cloud Scheduler + Cloud Run job.
2. **Learn Rust on a bounded, well-suited component:** a standalone `feed-ingest` CLI that fetches RSS/Atom + the HN Algolia endpoint, parses, dedupes, and scores/ranks items, emitting normalized JSON the Python editorial stage consumes. This is parsing-flavored, LLM-SDK-free, and a real daily-use tool — an ideal Rust teacher. Crates: `reqwest`, `tokio`, `serde`/`serde_json`, `feed-rs`, `clap`.
3. **If learning Rust is the *primary* goal** (app is just the vehicle — a legitimate choice, just be honest about it): build the whole thing in Rust eyes-open and accept the slower loop. Full crate stack: `reqwest` + `tokio` (fetch), `feed-rs` (feeds), `serde` (schema/JSON), `scraper` (HTML extraction), `askama` or `minijinja` (templating), an HTTP call to the LLM API (no mature SDK — hand-roll), and `clap` (CLI). PDF: render HTML and shell out to a headless browser, or use a Rust PDF crate for simpler layouts.

**Hosting:** a daily GCP Cloud Run job triggered by Cloud Scheduler fits your stack and costs ~nothing at this volume. Store editions in GCS; optionally email via an API or save to Drive.

---

## 9. Data model (sketch)

```
Source
  id, name, url/endpoint, method (rss|api|email|scrape|x),
  class (trusted|firehose), section, max_items, interest_tags[], enabled

Item
  id, source_id, title, canonical_url, author, published_at,
  raw_body, extracted_text, class, section (assigned),
  score (ranking), summary (LLM), dedupe_key, edition_id?

Edition
  id, date, edition_number, status (draft|final),
  item_ids[], read_time_estimate, pdf_path, archived_at

Almanac (per edition)
  edition_id, weather{}, your_day{first_meeting, count},
  french_holidays[], sports_week[], teams[]{team, last_result, next_fixture}

InterestProfile (single, you)
  topics_weighted{}, followed_teams[], location{lat,lng},
  edition_budget{max_items, per_section_caps}, schedule, delivery
```

---

## 10. MVP scope

**In (v1):**
- 6–10 sources across AI/LLM + tech/eng (RSS/API only): Willison, Import AI, HN (Algolia-filtered), Lobsters, Reddit (curated subs via PRAW), a couple of vendor/eng blogs.
- LLM editorial pass with a fixed item budget + per-section caps.
- Almanac: Your Day (Google Calendar), Weather (Open-Meteo), Your Teams (TheSportsDB).
- Render to print-ready PDF; deliver by email + archive to GCS.
- Schedule: weekday daily edition (early AM) + a weekend feature edition; both emailed as a print-ready PDF (you print) and archived to GCS.

**Deferred (v1.1+):**
- Newsletter ingest inbox (set up once v1's editorial quality is validated).
- French holidays + This Week in Sports Almanac modules.
- Personal-interest content sections (cooking, guitar).
- (X/Twitter intentionally dropped — see §5.6. Reddit replaces most of its value.)
- The Rust `feed-ingest` rewrite.
- E-ink output; auto-print to a physical printer; per-section read-time tuning.

**Success criterion for v1:** after a week of daily editions, you reliably read the edition and feel *caught up* without reopening any feed. Editorial quality (does it pick the right things and cut the rest?) is the metric — not feature count.

---

## 11. Roadmap

1. **Phase 0 — Spike (days):** one script, 3 RSS sources + HN, dump a ranked candidate list to the terminal. Validate the filter/rank logic before any rendering.
2. **Phase 1 — Editorial + render (week):** add the LLM editorial pass and HTML→PDF. Generate a real-looking edition daily by hand.
3. **Phase 2 — Almanac + delivery (week):** Calendar, Weather, Teams; auto-email + archive; Cloud Run + Scheduler.
4. **Phase 3 — Breadth (ongoing):** newsletter inbox, more sources, French-holiday + sports-week modules, personal sections.
5. **Phase 4 — Learn Rust:** rewrite `feed-ingest` as a Rust CLI feeding the Python editorial stage.

---

## 12. Risks & open questions

- **Editorial quality is the whole ballgame.** If the LLM pass picks poorly, the product fails regardless of engineering. Budget the most iteration here; consider a feedback loop (you mark items good/bad, profile adjusts).
- **Feed URLs move.** Confirm each feed/endpoint at build time; build adapters defensively (graceful skip on a dead source).
- **X access is expensive/risky** — keep it optional; don't let it block v1.
- **Newsletter parsing is messy** — the email→RSS bridge mitigates this; custom parsing only where it pays off.
- **"Finite" discipline is a product risk, not just a tech one** — resist the urge to raise the item cap. The constraint *is* the product.
- **Decided — cadence:** weekday daily edition (Mon–Fri) + a distinct weekend feature edition (one developed long-read, not a lighter version). See §4.0.
- **Decided — delivery:** email the print-ready PDF to yourself; you print manually (the printer isn't always on). Auto-print is *optional and deferred* — vendor email-to-print services are being sunset (test before relying on one), or use a small always-on local print server (Raspberry Pi + CUPS). Not worth the complexity for v1.
- **Decided — X/Twitter dropped** (see §5.6); Reddit + the existing sources replace it.
- **Open:** which day the weekend edition runs (Sat vs Sun); the curated subreddit set and per-source upvote thresholds (tune empirically).
