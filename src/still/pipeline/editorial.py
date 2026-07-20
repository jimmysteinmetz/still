"""EDITORIAL stage (spec §7) — the heart of the product.

Gemini pass over the ranked candidate pool + interest profile + edition
budget: selects within the caps, writes summaries, headlines the edition.
Trusted sources get a light touch; firehose sources get cut hard (spec §5).
The model proposes; `enforce_budget` disposes — quotas are enforced in code,
never trusted to the LLM.
"""

import json
import logging
import os
import re
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from still.config import StillConfig
from still.models import Item
from still.pipeline.layout import WORD_CAPS, capacity, split_wire

# EditionKind moved to pipeline/layout.py (the fixed-layout contract) — re-export
# so cli.py and callers keep addressing it as editorial.EditionKind.
from still.pipeline.layout import EditionKind as EditionKind
from still.pipeline.lessons import (
    brief_for,
    lesson_count_for,
    projected_item_count,
    topics_for,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.5-flash"
# Gemini on Vertex is served from the `global` endpoint — NOT a regional one like
# us-east4 (fine for other infra), which hosts no Gemini publisher models and 403s.
# Vertex needs a project: set GOOGLE_CLOUD_PROJECT (the gitignored .env works) plus
# a one-time `gcloud auth application-default login`, or set GEMINI_API_KEY to use
# the Developer API instead.
DEFAULT_LOCATION = "global"

# Vertex 429s here are quota ceilings, not load — one small call per build (the
# pipeline never fans out or retries on its own). A daily batch job has no latency
# budget to protect, so ride out transient 429s/5xx with SDK-native exponential
# backoff instead of crashing the edition. google-genai handles the loop internally
# (and honors Retry-After where present).
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=60.0,
    exp_base=2.0,
    http_status_codes=[429, 500, 502, 503, 504],
)


def _make_client() -> genai.Client:
    """Auth for Gemini. Default: Vertex AI + ADC on the global endpoint (no key to
    manage; Cloud Run's service account works as-is), which needs GOOGLE_CLOUD_PROJECT.
    Setting GEMINI_API_KEY opts into the Developer API instead. Both paths carry
    RETRY_OPTIONS so a transient 429 backs off rather than killing the build."""
    http_options = types.HttpOptions(retry_options=RETRY_OPTIONS)
    if os.environ.get("GEMINI_API_KEY"):
        return genai.Client(http_options=http_options)
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError(
            "Gemini auth is not configured. Set GOOGLE_CLOUD_PROJECT to a GCP project"
            " with Vertex AI enabled (and run `gcloud auth application-default login`"
            " once), or set GEMINI_API_KEY to use the Developer API. Both can live in"
            " the gitignored .env — see .env.example."
        )
    return genai.Client(
        vertexai=True,
        project=project,
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION),
        http_options=http_options,
    )


class Selection(BaseModel):
    item_id: str
    section: str
    headline: str
    summary: str
    # "pressing" lifts a story into the front block (ahead of the lessons); "brief"
    # is the default so a malfunctioning model just yields a normal sectioned paper.
    prominence: Literal["pressing", "brief"] = "brief"
    # A one-line standfirst the model writes for the marquee/lead, rendered as the
    # feature deck under the big headline. Empty for everything else; an empty deck
    # simply isn't rendered, so a model that omits it just loses the standfirst.
    deck: str = ""


class GlossaryEntry(BaseModel):
    """An uncommon acronym/term used in the edition, defined concisely."""

    term: str
    definition: str


class FrenchEntry(BaseModel):
    """An interesting French word or idiom with a concise English gloss."""

    word: str
    gloss: str


class Lesson(BaseModel):
    """One rotating "Margin" lesson the LLM writes for a code-chosen topic."""

    topic: str  # echoes the injected topic key, for traceability
    title: str  # short human-facing label, e.g. "Philosophy"
    body: str  # 2-4 engaging sentences


class EditorialResult(BaseModel):
    edition_headline: str
    selections: list[Selection]
    # Foot-of-page Lexicon. Additive text, not part of the item budget; counts are
    # still clamped in enforce_budget so the LLM can't pad the page.
    glossary: list[GlossaryEntry] = []
    french_vocab: list[FrenchEntry] = []
    # Rotating "Margin" lessons (between pressing and filler stories). Likewise
    # additive and likewise clamped in enforce_budget.
    lessons: list[Lesson] = []


# Lexicon caps — finite like everything else (spec §2).
MAX_GLOSSARY = 6
MAX_FRENCH = 4
# Safety valve against prompt bloat if dedup_lookback_days is raised toward its
# ceiling (config.py) — not expected to bind at the 7-day default.
MAX_RECENT_TOPICS = 150
# Same idea for the lesson/vocab history blocks below — lessons/vocab accumulate
# far slower than news items (a handful per edition), so these rarely bind either.
MAX_RECENT_LESSONS = 50
MAX_RECENT_FRENCH = 60
# Lesson count is dynamic (base per_edition, expanded on thin-news days to fill the
# page) — see pipeline/lessons.lesson_count_for. It's still pure code, never the LLM.


LEXICON_BRIEF = """\
Finally, ALWAYS compile a Lexicon for the foot of the page — both lists are
required, never leave them empty:
- glossary: 3 to {max_glossary} genuinely uncommon acronyms or terms that
  actually appear in the items you selected — define each in one concise clause.
  Skip anything a well-read generalist already knows; aim for the words that
  would make a reader pause. If the news is light, still find at least 3.
- french_vocab: 3 to {max_french} interesting or useful French words or idioms
  (need not come from the news) with a concise English gloss — a small daily
  indulgence for a Francophile reader. Vary them day to day.{avoid_french}"""

RECENT_TOPICS_BRIEF = """\
## Recently covered (last {days} days — do not re-select these stories)
Skip any candidate that covers the same underlying story as one of these
already-published headlines/topics, even if today's URL or headline reads
differently — a rewrite, a different outlet, or a minor follow-up all count
as "already covered." A genuinely new, substantial development in an ongoing
story (e.g. a major status change, a real sequel event) is fine to include.
{topic_lines}"""

LESSONS_BRIEF = """\
Also write {n} short "Margin" lesson(s) — one per topic below — to sit between the
pressing stories and the rest of the edition. Each is a self-contained, engaging
lesson of 2-4 sentences (timeless, not tied to today's news). Return them as
`lessons`, echoing the topic key in `topic` and a short human label in `title`.
Topics for this edition:
{topic_lines}"""

RECENT_LESSONS_BRIEF = """\
## Recently covered Margin lessons (last {days} days — write something different)
Even if today's topic category repeats, do not reuse the same fact, story, or
angle as any of these already-published lessons — pick a different example,
era, or angle instead.
{lesson_lines}"""

WEEKDAY_BRIEF = """\
You are the editor of a dense two-page personal daily newspaper. The reader's
contract: "Read this once and you are caught up. You will miss things, and that
is the feature." There is room for a substantial edition — aim to fill
both pages with what genuinely matters. Select close to {max_items} items when the
pool supports it; go lighter only when little is truly worth including, never pad
with weak items. Keep the sections balanced — lean on the busiest section to fill
space only when the others are thin. Never exceed {max_items} items total or any
section quota.

For each selected item write a crisp headline and a 2-3 sentence, 40 to 55 word
summary. Preserve every concrete detail from the source: exact numbers,
percentages, dollar figures, dates, and version numbers — and, critically, full
before/after values for any ranking, standing, or comparison ("climbed from #8
to #3," not "moved up the rankings"; "cut p99 latency from 800ms to 120ms," not
"significantly faster"). If the source states a specific figure, your summary
must state that figure, not a description of it. So the reader can skip the
original article entirely: cut connective and scene-setting prose before you
cut a fact. Trusted-source items deserve the benefit of the doubt; firehose
items must earn their place by clearly matching the reader's interests. Skip
engagement bait, outrage, and incremental news.

Set each item's `prominence`: mark exactly five stories "pressing" — they build
the front page — and everything else "brief". The single most important pressing
story anchors the front as the marquee: give it a 2 to 3 paragraph, 150 to 190
word treatment (held to the same requirement to preserve every concrete number,
rank, and before/after value) and also write a `deck`: a one-line standfirst of
at most 18 words that expands the headline with a hook. The other four pressing
stories fill the front row below the marquee — give each a fuller 70 to 90 word
summary. Leave `deck` empty for every other item. Word counts are enforced:
anything over its cap is machine-truncated at a sentence boundary, so write to
length rather than past it.

Also write one short edition headline capturing the day's theme.

{lessons}

{lexicon}"""

WEEKEND_BRIEF = """\
You are the editor of a weekend feature edition of a personal newspaper.
Pick exactly ONE marquee story most worth the reader's weekend attention and
develop it: a strong headline, a `deck` (a one-line standfirst of at most 18
words that expands the headline with a hook), and a 2 to 3 paragraph, 150 to
210 word treatment (what happened, context, why it matters to this reader).
Preserve every concrete detail from the source — exact numbers, percentages,
dollar figures, dates, and full before/after values for any ranking or
comparison ("climbed from #8 to #3," not "moved up the rankings") — a reader
should never have to open the original article to learn a figure you already
had. Then pick at most {max_items_minus_one} supporting quick hits (leave their
`deck` empty), held to the same standard: real figures, not vague gestures at
them. The first four hits you list lead the front page below the marquee — give
each a fuller 70 to 90 word summary; each remaining hit is a 1-2 sentence, 25
to 40 word summary. Word counts are enforced: anything over its cap is
machine-truncated at a sentence boundary, so write to length rather than past
it. Depth over breadth. Never exceed {max_items} items total. Also write one
edition headline.

Set the marquee story's `prominence` to "pressing" and the supporting hits to
"brief".

{lessons}

{lexicon}"""


def _finalize_french_vocab(
    entries: list[FrenchEntry], edition_number: int, recent_french: list[str]
) -> list[FrenchEntry]:
    """Hard backstop for the Lexicon's french_vocab: LEXICON_BRIEF only *asks* the
    model to vary words day to day and avoid the recent list — models don't always
    comply (this Lexicon has gone empty outright before, e.g. 2026-06-27). Drop any
    word seen in `recent_french`, then top up to at least 3 (LEXICON_BRIEF's stated
    minimum) from the avoid-aware fallback deck so a partially-repeated response
    gets fixed too, not just a fully-empty one."""
    from still.render.vocab import french_fallback

    avoid = set(recent_french)
    kept = [e for e in entries if e.word not in avoid]
    needed = max(3 - len(kept), 0)
    if needed:
        already = avoid | {e.word for e in kept}
        kept += [
            FrenchEntry(word=w, gloss=g)
            for w, g in french_fallback(edition_number, needed, avoid=already)
        ]
    return kept


def select_and_summarize(
    candidates: list[Item],
    cfg: StillConfig,
    kind: EditionKind,
    edition_number: int,
    recent_topics: list[str],
    recent_lessons: list[tuple[str, str, str]] | None = None,
    recent_french: list[str] | None = None,
) -> EditorialResult:
    # History (last dedup_lookback_days), not today's output — see result.lessons /
    # result.french_vocab below for what this edition actually produced.
    recent_lessons = recent_lessons or []
    recent_french = recent_french or []
    client = _make_client()
    try:
        response = client.models.generate_content(
            model=os.environ.get("STILL_GEMINI_MODEL", DEFAULT_MODEL),
            contents=build_prompt(
                candidates, cfg, kind, edition_number, recent_topics, recent_lessons, recent_french
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EditorialResult,
                temperature=0.4,
            ),
        )
    except errors.APIError as exc:
        # RETRY_OPTIONS already backed off; reaching here means the quota is
        # genuinely exhausted (or another API error). Fail loudly with a clear
        # cause — editorial is the heart of the edition, so re-raise rather than
        # emit an empty paper.
        logger.error(
            "editorial: Gemini request failed after %d attempts (code %s): %s",
            RETRY_OPTIONS.attempts,
            getattr(exc, "code", "?"),
            exc,
        )
        raise
    result = response.parsed
    if not isinstance(result, EditorialResult):
        result = EditorialResult.model_validate_json(response.text or "")
    result = enforce_budget(result, candidates, cfg, kind)
    # The Lexicon is a structural footer element now; never let it vanish or repeat
    # because the model declined to comply (it has, e.g. the 2026-06-27 edition).
    # Glossary is content-derived, so we can only flag an empty one rather than
    # invent terms.
    result.french_vocab = _finalize_french_vocab(result.french_vocab, edition_number, recent_french)
    if not result.glossary:
        logger.warning("editorial: model returned an empty glossary for this edition")
    return result


def build_prompt(
    candidates: list[Item],
    cfg: StillConfig,
    kind: EditionKind,
    edition_number: int,
    recent_topics: list[str],
    recent_lessons: list[tuple[str, str, str]] | None = None,
    recent_french: list[str] | None = None,
) -> str:
    # History (last dedup_lookback_days), not today's selections — see the
    # "Recently covered"/"Recently covered Margin lessons" prompt sections below.
    recent_lessons = recent_lessons or []
    recent_french = recent_french or []
    max_items = (cfg.edition.weekday if kind == "weekday" else cfg.edition.weekend).max_items
    if recent_french:
        avoid_french = (
            " Do not reuse any of these recently used words: "
            + ", ".join(dict.fromkeys(recent_french[:MAX_RECENT_FRENCH]))
            + "."
        )
    else:
        avoid_french = ""
    lexicon = LEXICON_BRIEF.format(
        max_glossary=MAX_GLOSSARY, max_french=MAX_FRENCH, avoid_french=avoid_french
    )
    if recent_topics:
        recent_topic_lines = "\n".join(
            f"- {t}" for t in dict.fromkeys(recent_topics[:MAX_RECENT_TOPICS])
        )
        recent_block = "\n\n" + RECENT_TOPICS_BRIEF.format(
            days=cfg.edition.dedup_lookback_days, topic_lines=recent_topic_lines
        )
    else:
        recent_block = ""
    projected = projected_item_count(candidates, cfg, max_items)
    topics = topics_for(edition_number, cfg, lesson_count_for(cfg, projected))
    if topics:
        topic_lines = "\n".join(f"- {t}: {brief_for(t, cfg)}" for t in topics)
        lessons = LESSONS_BRIEF.format(n=len(topics), topic_lines=topic_lines)
        if recent_lessons:
            lesson_lines = "\n".join(
                f"- [{topic}] {title}: {body}"
                for topic, title, body in recent_lessons[:MAX_RECENT_LESSONS]
            )
            lessons += "\n\n" + RECENT_LESSONS_BRIEF.format(
                days=cfg.edition.dedup_lookback_days, lesson_lines=lesson_lines
            )
    else:
        lessons = ""
    brief = (WEEKDAY_BRIEF if kind == "weekday" else WEEKEND_BRIEF).format(
        max_items=max_items, max_items_minus_one=max_items - 1, lessons=lessons, lexicon=lexicon
    )
    sections = "\n".join(
        f"- {s.id}: {s.title} (quota {s.max_items})"
        + (f"\n  Style guidance for {s.id}: {s.style}" if s.style else "")
        for s in cfg.sections
    )
    interests = "\n".join(f"- {i}" for i in cfg.interests)
    sources_in_pool = {i.source_name for i in candidates}
    source_quotas = "\n".join(
        f"- {s.name}: at most {s.max_items}" + (f"\n  Note on {s.name}: {s.note}" if s.note else "")
        for s in cfg.sources
        if s.name in sources_in_pool
    )
    pool = "\n".join(
        json.dumps(
            {
                "id": i.id,
                "section": i.section,
                "source": i.source_name,
                "class": i.class_,
                "title": i.title,
                "excerpt": (i.raw_body or "")[:500],
                "url": i.canonical_url,
            }
        )
        for i in candidates
    )
    return (
        f"{brief}\n\n## Reader interests\n{interests}"
        f"{recent_block}\n\n"
        f"## Sections and quotas\n{sections}\n\n"
        f"## Per-source caps (one source must not dominate)\n{source_quotas}\n\n"
        f"## Candidate pool (one JSON object per line)\n{pool}\n\n"
        "Return your selection. Use each item's `id` as `item_id` and assign "
        "a `section` id from the list above."
    )


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _truncate_words(text: str, max_words: int) -> str:
    """Clamp text to at most max_words — the guarantee behind the fixed layout
    (prompts only *ask* for a length; this enforces it). Prefers dropping whole
    trailing sentences so the cut is invisible; if even the first sentence
    exceeds the cap, hard-cut at a word boundary with an ellipsis (rare — the
    prompt targets sit well under the caps; warn so it's visible in build logs)."""
    words = text.split()
    if len(words) <= max_words:
        return text
    kept: list[str] = []
    total = 0
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        n = len(sentence.split())
        if total + n > max_words:
            break
        kept.append(sentence)
        total += n
    if kept:
        return " ".join(kept)
    logger.warning("editorial: hard-truncating a %d-word run-on to %d words", len(words), max_words)
    return " ".join(words[:max_words]).rstrip(".,;:—–-") + "…"


def _truncate_selection(
    sel: Selection, summary_cap: int, deck_cap: int, headline_cap: int
) -> Selection:
    update = {
        "summary": _truncate_words(sel.summary, summary_cap),
        "headline": _truncate_words(sel.headline, headline_cap),
    }
    if sel.deck:
        update["deck"] = _truncate_words(sel.deck, deck_cap)
    return sel.model_copy(update=update)


def enforce_budget(
    result: EditorialResult, candidates: list[Item], cfg: StillConfig, kind: EditionKind
) -> EditorialResult:
    """Clamp the model's selection to the hard caps; drop unknown/duplicate ids.
    Also clamps every text field to the fixed layout's WORD_CAPS — the two-page
    geometry only holds if no summary can outgrow its box."""
    configured = (cfg.edition.weekday if kind == "weekday" else cfg.edition.weekend).max_items
    # config may ask for fewer stories than the fixed layout holds, never more.
    max_items = min(configured, capacity(kind))
    by_id = {i.id: i for i in candidates}
    section_ids = {s.id for s in cfg.sections}
    section_caps = {s.id: s.max_items for s in cfg.sections}
    source_caps = {s.name: s.max_items for s in cfg.sources}

    kept: list[Selection] = []
    used: set[str] = set()
    counts: dict[str, int] = dict.fromkeys(section_ids, 0)
    source_counts: dict[str, int] = {}
    for sel in result.selections:
        item = by_id.get(sel.item_id)
        if item is None or sel.item_id in used:
            logger.warning("editorial: dropping unknown/duplicate item_id %s", sel.item_id)
            continue
        section = sel.section if sel.section in section_ids else item.section
        if counts[section] >= section_caps[section]:
            logger.warning("editorial: section %s over quota, dropping %r", section, sel.headline)
            continue
        source_cap = source_caps.get(item.source_name, max_items)
        if source_counts.get(item.source_name, 0) >= source_cap:
            logger.warning(
                "editorial: source %s over quota, dropping %r", item.source_name, sel.headline
            )
            continue
        if len(kept) >= max_items:
            break
        counts[section] += 1
        source_counts[item.source_name] = source_counts.get(item.source_name, 0) + 1
        used.add(sel.item_id)
        kept.append(sel.model_copy(update={"section": section}))
    # Lesson count: build_prompt asked the model for lesson_count_for(pool projection)
    # lessons — a PRE-HOC estimate of how full the day would be, based on what the
    # candidate pool could support. But the LLM's actual pick (`kept`, just computed
    # above) can come in thinner than the pool projected (a conservative selection on
    # a rich-pool day) — in which case the pre-hoc request under-asked for lessons and
    # nothing was there to fill the resulting thin page (TASK-5). We can't conjure
    # lesson content the model was never asked to write, but we also must not clamp
    # away lessons it *did* return just because an optimistic pool estimate said
    # fewer were "needed". So recompute the target from the actual selection count
    # and take the larger of the two:
    #   - actual selection thinner than the pool projection -> lesson_count_for(actual)
    #     is >= the pre-hoc request (fewer items means more shortfall), so this loosens
    #     the clamp and lets any lessons beyond the pre-hoc ask survive.
    #   - actual selection at or above the projection -> lesson_count_for(actual) is
    #     <= the pre-hoc request, so max() leaves the original (base/pre-hoc) clamp
    #     alone rather than tightening it further; that count already assumed a full
    #     day, so there's nothing to correct.
    # Either way lesson_count_for's own ceilings (HARD_MAX_LESSONS, deck size) still
    # bind, and slicing result.lessons can never exceed what the model actually wrote.
    projected = projected_item_count(candidates, cfg, max_items)
    requested_lessons = lesson_count_for(cfg, projected)
    actual_lessons = lesson_count_for(cfg, len(kept))
    max_lessons = max(requested_lessons, actual_lessons)
    return clamp_to_layout(
        EditorialResult(
            edition_headline=result.edition_headline,
            selections=kept,
            glossary=result.glossary[:MAX_GLOSSARY],
            french_vocab=result.french_vocab[:MAX_FRENCH],
            lessons=result.lessons[:max_lessons],
        ),
        kind,
    )


def clamp_to_layout(result: EditorialResult, kind: EditionKind) -> EditorialResult:
    """Truncate every text field to the fixed layout's WORD_CAPS, by tier: the
    marquee and the four front-row stories get fuller allowances than the page-2
    briefs. Uses the SAME split_wire as render_html, so each story is truncated
    to the box it will land in. Called by enforce_budget; also used by
    scripts/smoke_render.py so offline fixtures carry exactly the text lengths
    production would."""
    caps = WORD_CAPS[kind]
    marquee, front, _rest = split_wire(result.selections, kind)
    marquee_id = marquee.item_id if marquee is not None else None
    front_ids = {s.item_id for s in front}

    def _summary_cap(sel: Selection) -> int:
        if sel.item_id == marquee_id:
            return caps["marquee"]
        return caps["front"] if sel.item_id in front_ids else caps["brief"]

    return EditorialResult(
        edition_headline=_truncate_words(result.edition_headline, caps["theme"]),
        selections=[
            _truncate_selection(s, _summary_cap(s), caps["deck"], caps["headline"])
            for s in result.selections
        ],
        glossary=[
            g.model_copy(update={"definition": _truncate_words(g.definition, caps["gloss"])})
            for g in result.glossary
        ],
        french_vocab=[
            f.model_copy(update={"gloss": _truncate_words(f.gloss, caps["french"])})
            for f in result.french_vocab
        ],
        lessons=[
            les.model_copy(update={"body": _truncate_words(les.body, caps["lesson"])})
            for les in result.lessons
        ],
    )
