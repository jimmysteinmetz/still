"""Manual smoke test: render a realistic edition to PDF via `uv run scripts/smoke_render.py`.

Uses fabricated-but-realistic content (lengths matching a real Gemini edition)
so the newspaper layout can be tuned without live LLM calls.
"""

import io
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from still.almanac.calendar import YourDay
from still.almanac.shows import ShowRow
from still.almanac.sports import ScoreRow
from still.almanac.weather import Weather
from still.config import load_config
from still.models import Item
from still.pipeline.editorial import (
    EditorialResult,
    FrenchEntry,
    GlossaryEntry,
    Lesson,
    Selection,
)
from still.render import badges
from still.render.html import render_html
from still.render.pdf import _weasyprint_env, html_to_pdf

# (section, source, headline, summary)
CONTENT = [
    (
        "ai",
        "Simon Willison",
        "Anthropic Reverses Course on Claude's AI Research Safeguards",
        "Anthropic has apologized and walked back a controversial policy that could have "
        "invisibly sabotaged AI researchers using their Claude models. The change makes "
        "safeguards for frontier development legible again, and restores trust with a wary "
        "research community that had threatened to migrate to open-weight alternatives. The "
        "original policy would have let the company silently degrade outputs for flagged "
        "research workloads, a capability critics called a backdoor on independent evaluation. "
        "Anthropic now says any such intervention will be logged and disclosed, and that "
        "external auditors will get a documented appeals path. The episode lands as labs weigh "
        "how much of their evaluation stack they are willing to rent from a single vendor.",
    ),
    (
        "ai",
        "Latent Space",
        "Reflecting on Open Models, Agent Labs, and Untrainable AI",
        "A wide-ranging essay contrasts 'model labs' chasing foundational scale with 'agent "
        "labs' building autonomous systems atop them, arguing the split explains why two "
        "well-funded companies can pursue opposite strategies and both stay profitable. The "
        "durable moats, it argues, are shifting from raw parameter count toward orchestration, "
        "evals, and distribution.",
    ),
    (
        "ai",
        "Simon Willison",
        "datasette-agent 0.2a0 Introduces Interactive Tools",
        "The latest alpha lets tools ask the user questions mid-execution, enabling more "
        "dynamic agentic workflows instead of one-shot prompts.",
    ),
    (
        "ai",
        "Hugging Face blog",
        "Google's DiffusionGemma Delivers 4x Faster Text Generation",
        "Google re-released its experimental Gemini Diffusion model as DiffusionGemma, reporting "
        "roughly 857 tokens per second on short completions — a fourfold speedup over the 210 "
        "tokens per second its best comparable autoregressive baseline manages, though quality "
        "on longer, multi-step generations still trails the autoregressive models it's compared "
        "against.",
    ),
    (
        "eng",
        "Lobsters",
        "Discord Migrates Voice Infrastructure to the Edge",
        "Discord details moving real-time voice to edge points of presence to cut latency and "
        "improve reliability, with a candid post-mortem of the migration's rough edges.",
    ),
    (
        "eng",
        "Hacker News",
        "Apache Burr: Building Reliable AI Agents and Applications",
        "A new framework offers state machines and observability for agentic apps, aiming to "
        "make long-running LLM workflows debuggable and resumable rather than opaque black "
        "boxes. Early adopters report cutting a typical multi-step agent's failure-diagnosis "
        "time from a full afternoon of log-spelunking down to a few minutes.",
    ),
    (
        "eng",
        "Lobsters",
        "Introducing hax: A Rust Verification Tool",
        "An open-source tool formally verifies properties of Rust code, targeting correctness "
        "and security for cryptographic and systems libraries where a single bug can be "
        "catastrophic. The maintainers report it caught three memory-safety issues in a widely "
        "used crypto crate that years of fuzzing and code review had missed.",
    ),
    (
        "cloud",
        "Google Cloud blog",
        "Lightning Engine Boosts Apache Spark by 4.9x",
        "Google Cloud's Lightning Engine accelerates Spark workloads up to 4.9 times by fusing "
        "operators and optimizing shuffle, with benchmarks across common ETL jobs.",
    ),
    (
        "cloud",
        "Google Cloud blog",
        "BigQuery Adds Native Vector Search at Petabyte Scale",
        "A new index brings approximate nearest-neighbor search directly into BigQuery, letting "
        "analysts join embeddings against warehouse tables without standing up a separate "
        "vector store. Google reports sub-100ms query latency at a billion-row scale, and early "
        "customers say it cut their retrieval-pipeline infrastructure down to a single service.",
    ),
    (
        "personal",
        "Smitten Kitchen",
        "A Summer Tomato Tart That Actually Holds Together",
        "A blind-baked shell, a thin layer of mustard, and salted, drained tomatoes keep this "
        "tart crisp rather than soggy — a weeknight-friendly use for a glut of June tomatoes.",
    ),
    (
        "ai",
        "Import AI (Jack Clark)",
        "Open-Weight Models Keep Closing the Gap on Frontier Labs",
        "A new round of open-weight releases lands within two to three points of closed "
        "frontier models on reasoning and coding benchmarks, closing a gap that stood at over "
        "ten points a year ago. The piece argues the practical moat is shifting from raw "
        "capability to deployment, safety tooling, and inference cost.",
    ),
    (
        "ai",
        "Simon Willison",
        "Structured Output Becomes Table Stakes Across LLM APIs",
        "Every major provider now enforces JSON-schema-constrained decoding server-side, making "
        "tool calls reliable enough to build on without retry loops. The post benchmarks latency "
        "overhead and flags where strict schemas still trip models up.",
    ),
    (
        "eng",
        "Hacker News",
        "SQLite Ships Native JSON Indexing in 3.47",
        "The release adds indexes over JSON paths, letting embedded apps query document-shaped "
        "data without a separate store. Early benchmarks show order-of-magnitude speedups on "
        "filtered reads of large JSON columns.",
    ),
    (
        "eng",
        "Julia Evans",
        "A Field Guide to Reading strace Output",
        "A practical walkthrough of decoding syscall traces to debug hangs and missing files, "
        "with annotated examples of the dozen or so patterns that actually matter day to day "
        "rather than the hundreds documented in the man pages. The author's own hang-diagnosis "
        "time dropped from hours to under ten minutes once the patterns clicked.",
    ),
    (
        "eng",
        "Lobsters",
        "Why Your CI Is Slow: A Cache-Locality Story",
        "A debugging narrative traces a 20-minute pipeline to cold dependency caches and fan-out "
        "without affinity, then halves it with warm layers and pinned runners.",
    ),
    (
        "cloud",
        "Google Cloud blog",
        "Cloud Run Adds GPU-Backed Services in More Regions",
        "Serverless GPU instances for Cloud Run expand to additional regions with scale-to-zero "
        "billing, aimed at bursty inference workloads that don't justify a standing cluster.",
    ),
    (
        "personal",
        "r/guitar",
        "The Case for Learning on a Cheap Guitar First",
        "A well-argued thread: a $150 setup-adjusted instrument removes the fear of mistakes that "
        "stalls beginners, and the money is better spent on lessons than on tone. Several "
        "commenters who started on sub-$200 guitars and only upgraded after a year say the "
        "cheap instrument never actually held their progress back.",
    ),
    (
        "personal",
        "Smitten Kitchen",
        "Cold-Brew Concentrate Without the Bitterness",
        "Coarse grounds, a 16-hour steep at room temperature, and a paper filter yield a smooth "
        "concentrate that keeps a week — diluted one-to-one over ice.",
    ),
    (
        "personal",
        "r/guitar",
        "Restoring a 1970s Solid-State Amp on a Budget",
        "A step-by-step on recapping, cleaning scratchy pots, and safely draining filter caps to "
        "bring a thrift-store combo back to life without a tech.",
    ),
]

# Front stories lifted out of their sections, ahead of The Margin. The first
# pressing item (lowest index) keeps the drop-capped lead treatment.
PRESSING_IDX = {0, 4, 7}

cfg = load_config()
items = {
    f"i{n}": Item(
        id=f"i{n}",
        source_name=src,
        title=head,
        canonical_url=f"https://example.com/{section}/{n}",
        published_at=datetime.now(UTC),
        class_="trusted",
        section=section,
    )
    for n, (section, src, head, _summary) in enumerate(CONTENT)
}
result = EditorialResult(
    edition_headline="AI Policy Shifts, Agent Tools Evolve, and Cloud Speeds Up",
    selections=[
        Selection(
            item_id=f"i{n}",
            section=section,
            headline=head,
            summary=summary,
            prominence="pressing" if n in PRESSING_IDX else "brief",
            deck=(
                "Anthropic walks back a policy that could have quietly sabotaged "
                "researchers — and moves to rebuild trust with a wary field."
                if n == 0
                else ""
            ),
        )
        for n, (section, _src, head, summary) in enumerate(CONTENT)
    ],
    glossary=[
        GlossaryEntry(
            term="RAG",
            definition="retrieval-augmented generation; grounding an LLM in fetched documents",
        ),
        GlossaryEntry(
            term="autoregressive",
            definition="generating a sequence one token at a time, each conditioned on the last",
        ),
        GlossaryEntry(
            term="PoP",
            definition="point of presence; an edge server placed close to users to cut latency",
        ),
        GlossaryEntry(
            term="eval",
            definition="a structured test set scoring a model's quality on a specific task",
        ),
    ],
    french_vocab=[
        FrenchEntry(word="flâner", gloss="to stroll without aim, savoring the city"),
        FrenchEntry(word="le quotidien", gloss="the daily; everyday life, or a daily paper"),
        FrenchEntry(
            word="déjà-lu",
            gloss="lit. 'already read' — the news fatigue of seeing the same story everywhere",
        ),
    ],
    lessons=[
        Lesson(
            topic="philosophy",
            title="Philosophy",
            body="The Stoics drew a hard line between what is 'up to us' (our judgments and "
            "actions) and what is not (everything else). Epictetus argued that anxiety lives "
            "entirely in the second category — so the discipline is to spend attention only "
            "on the first.",
        ),
        Lesson(
            topic="ny_knowledge",
            title="New York",
            body="The numbered street grid above Houston comes from the 1811 Commissioners' "
            "Plan, which imposed a rectilinear lattice on still-rural Manhattan. Broadway "
            "predates it — an old Lenape trail — which is why it cuts diagonally across the "
            "grid, creating the open 'squares' at Times, Herald, and Madison.",
        ),
    ],
)
weather = Weather(
    label="New York", temp=74, high=82, low=64, icon="partly", condition="Partly cloudy"
)
your_day = YourDay(
    meeting_count=5, first_time="9:30 AM", first_title="Standup", last_time="4:00 PM"
)


def _crest(letter: str) -> str:
    """A stand-in monochrome crest (drawn letter) run through the real badge pipeline.

    Today's slate is mostly off-season, so this fabricates an in-season look to tune
    the scorebug layout offline — the same grayscale path live crests take.
    """
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 94, 94), outline=(20, 20, 20, 255), width=5)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 54)
    except OSError:
        font = ImageFont.load_default()
    d.text((50, 52), letter, fill=(20, 20, 20, 255), anchor="mm", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return badges._process(buf.getvalue())


sports = [
    ScoreRow(
        label="SPURS",
        us_badge=_crest("T"),
        mode="result",
        score="0–2",
        last_opp_badge=_crest("C"),
        next_token="Sat @",
        next_opp_badge=_crest("M"),
    ),
    ScoreRow(
        label="49ERS",
        us_badge=_crest("SF"),
        mode="result",
        score="24–17",
        last_opp_badge=_crest("LA"),
        next_token="Sun v",
        next_opp_badge=_crest("S"),
    ),
    ScoreRow(
        label="COLTS",
        us_badge=_crest("I"),
        mode="countdown",
        next_token="opens in 9d v",
        next_opp_badge=_crest("NE"),
    ),
    ScoreRow(
        label="INDYCAR",
        us_badge=_crest("IC"),
        mode="race",
        venue="Long Beach",
        next_token="in 6d",
    ),
]

shows = [
    ShowRow(
        artist="Lake Street Dive",
        date=date(2026, 8, 2),
        date_token="Aug 2",
        venue="Beacon Theatre",
        city="New York",
    ),
    ShowRow(
        artist="Vulfpeck",
        date=date(2026, 9, 9),
        date_token="Sep 9",
        venue="Madison Square Garden",
        city="New York",
    ),
    ShowRow(
        artist="Lizzy McAlpine",
        date=date(2026, 9, 21),
        date_token="Sep 21",
        venue="Brooklyn Paramount",
        city="Brooklyn",
    ),
]

# A thin weekend edition: one developed marquee + a handful of hits + expanded
# lessons — the shape that used to strand half a page. Should now fit one full page
# (footer included, no orphan). The marquee runs long, as a real weekend lead would.
WEEKEND_MARQUEE = (
    "Anthropic has apologized and walked back a controversial policy that could have "
    "invisibly sabotaged AI researchers using its Claude models, after a week of mounting "
    "pressure from labs that had threatened to migrate to open-weight alternatives. The "
    "reversal makes safeguards for frontier development legible again and, more importantly, "
    "restores the trust of a research community that had begun to treat the company's tooling "
    "as adversarial. "
    "The episode crystallizes a tension the whole field now lives with: the same infrastructure "
    "that makes a model useful for research also makes it a lever of control. When that lever "
    "moved without warning, researchers discovered how little of their own stack they actually "
    "owned. The practical lesson is the one local-first advocates have pressed for a year — that "
    "reproducibility and independence are features, not paranoia. "
    "For a working engineer the takeaway is concrete: keep an open-weight escape hatch warm, and "
    "treat any single provider's policy as mutable rather than load-bearing."
)
# Weekend quick hits target a tighter word count (25-40) than weekday briefs
# (40-55) per the editorial prompt, so a few CONTENT entries lengthened for the
# weekday fixture need a shorter override here to keep this a realistic proxy.
WEEKEND_HIT_OVERRIDES = {
    1: "A wide-ranging essay contrasts 'model labs' chasing foundational scale with 'agent "
    "labs' building autonomous systems atop them — arguing the durable moats are shifting "
    "from raw parameter count toward orchestration and distribution.",
    5: "A new framework offers state machines and observability for agentic apps, making "
    "long-running LLM workflows debuggable and resumable rather than opaque black boxes "
    "for on-call engineers.",
    13: "A practical walkthrough of decoding syscall traces to debug hangs and missing "
    "files, with annotated examples of the patterns that actually matter day to day.",
    16: "A well-argued thread: a $150 setup-adjusted instrument removes the fear of "
    "mistakes that stalls beginners, and the money is better spent on lessons than on tone.",
}
weekend = EditorialResult(
    edition_headline="A Trust Reset in AI, and the Quiet Case for Owning Your Stack",
    selections=[
        Selection(
            item_id="i0",
            section="ai",
            headline=CONTENT[0][2],
            summary=WEEKEND_MARQUEE,
            prominence="pressing",
            deck="Anthropic's reversal is a reminder of how little of their stack researchers "
            "actually own — and why a local-first escape hatch matters.",
        ),
        *[
            Selection(
                item_id=f"i{n}",
                section=CONTENT[n][0],
                headline=CONTENT[n][2],
                summary=WEEKEND_HIT_OVERRIDES.get(n, CONTENT[n][3]),
                prominence="brief",
            )
            for n in (1, 5, 7, 9, 13, 16)
        ],
    ],
    glossary=result.glossary[:3],
    french_vocab=result.french_vocab[:3],
    lessons=[
        *result.lessons,
        Lesson(
            topic="cybersecurity",
            title="Least Privilege",
            body="Grant every user and service the minimum access it needs. It caps the blast "
            "radius when an account is compromised, and routine audits stop 'privilege creep.'",
        ),
        Lesson(
            topic="french_culture",
            title="The Flâneur",
            body="To 'flâner' is to stroll the city with no destination, reading it like a text — "
            "a habit 19th-century Parisian writers turned into an art.",
        ),
    ],
)


def _page_count(html: str) -> int | None:
    """Page count via WeasyPrint (independent of which engine html_to_pdf ends up
    using) — cheap way to report pagination without adding a PDF-parsing dependency
    just for this manual smoke test. Runs in a subprocess with the same dylib-path
    injection as render/pdf.py: an in-process import can't see a DYLD path set
    after launch, so it would crash on a stock macOS shell. Merely informational,
    so any failure returns None instead of killing the smoke run."""
    code = (
        "import sys; from weasyprint import HTML; "
        "print(len(HTML(string=sys.stdin.read()).render().pages))"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=html,
            text=True,
            capture_output=True,
            timeout=45,
            check=True,
            env=_weasyprint_env(),
        )
        return int(proc.stdout.strip())
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


# TASK-5 repro: a conservative real selection on a day the pool could have filled
# (few items, most sections empty) — the shape that used to strand a near-empty
# trailing page (1-2 Wire items + Lexicon) under a fixed 4-column layout. Uses its
# own item ids/dict since it draws on only a handful of CONTENT rows.
THIN_IDX = [0, 4, 7, 9]  # one per section: ai, eng, cloud, personal
thin_items = {
    f"i{n}": Item(
        id=f"i{n}",
        source_name=CONTENT[n][1],
        title=CONTENT[n][2],
        canonical_url=f"https://example.com/{CONTENT[n][0]}/{n}",
        published_at=datetime.now(UTC),
        class_="trusted",
        section=CONTENT[n][0],
    )
    for n in THIN_IDX
}
thin = EditorialResult(
    edition_headline="A Quiet News Day",
    selections=[
        Selection(
            item_id="i0",
            section="ai",
            headline=CONTENT[0][2],
            summary=CONTENT[0][3],
            prominence="pressing",
            deck="Anthropic walks back a policy that could have quietly sabotaged "
            "researchers — and moves to rebuild trust with a wary field.",
        ),
        *[
            Selection(
                item_id=f"i{n}",
                section=CONTENT[n][0],
                headline=CONTENT[n][2],
                summary=CONTENT[n][3],
            )
            for n in THIN_IDX[1:]
        ],
    ],
    # Full Lexicon (4 glossary + 3 French = 7 rows) — this is exactly the volume
    # that used to force the whole footer onto its own near-empty trailing page
    # under a fixed 4-column layout (see the .lex-cols comment in the template).
    glossary=result.glossary,
    french_vocab=result.french_vocab,
    # Adaptive lesson count would expand past the base 2 on a day this thin (see
    # pipeline/lessons.lesson_count_for) — modeled directly here since this script
    # renders straight from a hand-built EditorialResult, bypassing
    # editorial.enforce_budget (covered separately in tests/test_editorial.py).
    lessons=[
        *result.lessons,
        Lesson(
            topic="cybersecurity",
            title="Least Privilege",
            body="Grant every user and service the minimum access it needs. It caps the blast "
            "radius when an account is compromised, and routine audits stop 'privilege creep.'",
        ),
    ],
)


def _build_and_write(
    res: EditorialResult,
    *,
    kind: str,
    edition_number: int,
    date_display: str,
    out_name: str,
    items_by_id: dict[str, Item] | None = None,
) -> None:
    html = render_html(
        res,
        items_by_id if items_by_id is not None else items,
        cfg,
        date_display=date_display,
        edition_number=edition_number,
        kind=kind,
        weather=weather,
        sports=sports,
        shows=shows,
        your_day=your_day if kind == "weekday" else None,
    )
    out = Path(out_name)
    engine = html_to_pdf(html, out)
    pages = _page_count(html)
    pages_display = pages if pages is not None else "?"
    size = out.stat().st_size
    print(f"[{kind}] engine={engine} size={size} bytes pages={pages_display} -> {out}")


_build_and_write(
    result,
    kind="weekday",
    edition_number=1,
    date_display="Thursday, June 11, 2026",
    out_name="data/smoke-edition.pdf",
)
_build_and_write(
    weekend,
    kind="weekend",
    edition_number=2,
    date_display="Saturday, June 27, 2026",
    out_name="data/smoke-edition-weekend.pdf",
)
_build_and_write(
    thin,
    kind="weekday",
    edition_number=3,
    date_display="Tuesday, June 30, 2026",
    out_name="data/smoke-edition-thin.pdf",
    items_by_id=thin_items,
)
