"""CLI entrypoint: `uv run still <command>`."""

import logging
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import httpx
import typer
from dotenv import load_dotenv
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from still import db
from still.almanac import calendar as calendar_mod
from still.almanac import shows as shows_mod
from still.almanac import sports as sports_mod
from still.almanac import weather as weather_mod
from still.almanac.calendar import YourDay
from still.almanac.shows import ShowRow
from still.almanac.sports import ScoreRow
from still.almanac.weather import Weather
from still.config import (
    DEFAULT_CONFIG_PATH,
    HnAlgoliaSource,
    RedditSource,
    RssSource,
    StillConfig,
    load_config,
)
from still.ingest import hn, reddit, rss
from still.models import Edition, Item
from still.pipeline import editorial
from still.pipeline.dedupe import dedupe
from still.pipeline.rank import rank
from still.render.html import estimate_read_time_min, render_html
from still.render.pdf import html_to_pdf

USER_AGENT = "still/0.1 (personal newspaper digest; +https://github.com/jimmysteinmetz/still)"

# Load local secrets from a gitignored .env (e.g. SEATGEEK_CLIENT_ID). In prod these
# come from Secret Manager → the Cloud Run env, which already wins: load_dotenv never
# overrides a variable that's already set in the environment.
load_dotenv()

app = typer.Typer(no_args_is_help=True, help="still — personal newspaper pipeline.")
config_app = typer.Typer(no_args_is_help=True, help="Inspect and validate config/still.yaml.")
app.add_typer(config_app, name="config")
calendar_app = typer.Typer(no_args_is_help=True, help="Google Calendar (Your Day) setup.")
app.add_typer(calendar_app, name="calendar")

console = Console()


def _calendar_client_path() -> Path:
    return Path(os.environ.get("GOOGLE_CALENDAR_CLIENT", "data/google_calendar_client.json"))


def _calendar_token_path() -> Path:
    return Path(os.environ.get("GOOGLE_CALENDAR_TOKEN", "data/google_calendar_token.json"))


@config_app.command("check")
def config_check(
    path: Annotated[
        Path, typer.Option("--path", help="Config file to check.")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Validate the config and print the resolved edition plan."""
    try:
        cfg = load_config(path)
    except FileNotFoundError:
        console.print(f"[red]Config file not found:[/red] {path}")
        raise typer.Exit(1) from None
    except ValidationError as e:
        console.print(f"[red]Config invalid[/red] ({path}):")
        for err in e.errors():
            loc = " → ".join(str(p) for p in err["loc"])
            console.print(f"  [yellow]{loc}[/yellow]: {err['msg']}")
        raise typer.Exit(1) from None

    _print_edition_plan(cfg)
    console.print("[green]Config OK[/green]")


@calendar_app.command("auth")
def calendar_auth() -> None:
    """One-time OAuth consent so Your Day can read your calendar unattended.

    Opens a browser to consent with your Google account, then stores an
    authorized-user token. Needs a Desktop-app OAuth client secret (Calendar API
    enabled) at GOOGLE_CALENDAR_CLIENT (default data/google_calendar_client.json).
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_path = _calendar_client_path()
    token_path = _calendar_token_path()
    if not client_path.exists():
        console.print(
            f"[red]OAuth client secret not found:[/red] {client_path}\n"
            "Create a Desktop-app OAuth client (Google Calendar API enabled) in your "
            "GCP project, download the JSON there, or point GOOGLE_CALENDAR_CLIENT at it."
        )
        raise typer.Exit(1)
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), calendar_mod.SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    console.print(f"[green]Authorized[/green] — token saved to {token_path}")


def _print_edition_plan(cfg: StillConfig) -> None:
    e = cfg.edition
    console.print(
        f"\n[bold]Edition plan[/bold]  ·  weekday ≤ {e.weekday.max_items} items"
        f"  ·  weekend ≤ {e.weekend.max_items} items"
        f" (long-read, {e.weekend.day})  ·  tz {e.timezone}\n"
    )

    table = Table(show_lines=False)
    table.add_column("Section")
    table.add_column("Quota", justify="right")
    table.add_column("Sources")
    for section in cfg.sections:
        sources = cfg.sources_for(section.id)
        listing = "\n".join(f"{s.name}  ({s.class_}, ≤{s.max_items})" for s in sources) or "—"
        table.add_row(f"{section.title} ({section.id})", str(section.max_items), listing)
    console.print(table)

    a = cfg.almanac
    teams_on = [t for t in a.teams if t.enabled]
    series_on = [s for s in a.series if s.enabled]
    lessons_on = a.lessons.enabled and bool(a.lessons.deck)
    shows_on = a.shows.enabled and bool(a.shows.artists)
    modules = [
        ("Your Day", a.your_day.enabled),
        ("Weather", a.weather.enabled),
        ("Scoreboard", bool(teams_on or series_on)),
        ("Shows", shows_on),
        ("Lessons", lessons_on),
        ("French holidays", a.french_holidays.enabled),
        ("Sports week", a.sports_week.enabled),
    ]
    on = ", ".join(name for name, enabled in modules if enabled)
    off = ", ".join(name for name, enabled in modules if not enabled)
    console.print(f"\nAlmanac on: {on}")
    if off:
        console.print(f"Almanac off: {off}")
    followed = [t.short or t.name for t in teams_on] + [s.short or s.name for s in series_on]
    if followed:
        console.print(f"Scoreboard follows: {', '.join(followed)}")
    if lessons_on:
        console.print(
            f"Lessons deck: {len(a.lessons.deck)} topics, {a.lessons.per_edition}/edition"
        )
    if shows_on:
        key = "set" if os.environ.get("SEATGEEK_CLIENT_ID") else "MISSING SEATGEEK_CLIENT_ID"
        console.print(f"Shows: {len(a.shows.artists)} artists, {key}")
    if a.your_day.enabled:
        tok = (
            "token set"
            if _calendar_token_path().exists()
            else "MISSING — run 'still calendar auth'"
        )
        console.print(f"Your Day: calendar {a.your_day.calendar_id}, {tok}")
    console.print(f"Interests: {len(cfg.interests)}  ·  Delivery: {cfg.delivery.email}\n")


@app.command()
def candidates(
    hours: Annotated[int, typer.Option(help="Lookback window for candidates.")] = 24,
    mark_seen: Annotated[
        bool,
        typer.Option("--mark-seen", help="Record shown items so they don't reappear tomorrow."),
    ] = False,
) -> None:
    """Fetch, dedupe, rank, and print the candidate pool (no LLM, no PDF)."""
    cfg = load_config()
    conn = db.connect()
    pool = _candidate_pool(cfg, conn, hours)
    _print_candidates(pool, cfg)
    if mark_seen:
        db.mark_seen(conn, pool)
        console.print(f"[dim]Recorded {len(pool)} items in seen history.[/dim]")
    conn.close()


@app.command()
def build(
    hours: Annotated[int, typer.Option(help="Lookback window for candidates.")] = 24,
    kind: Annotated[str, typer.Option(help="weekday | weekend | auto (by day of week).")] = "auto",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run editorial + render but don't archive or mark seen."),
    ] = False,
) -> None:
    """Build today's edition: fetch → dedupe → rank → editorial (Gemini) → PDF."""
    cfg = load_config()
    tz = ZoneInfo(cfg.edition.timezone)
    today = datetime.now(tz)
    edition_kind = _resolve_kind(kind, today, cfg)

    conn = db.connect()
    # Non-mutating SELECT, safe to read early — feeds both the dedupe() cross-day
    # title backstop and the editorial "recently covered" prompt section (TASK-3).
    since_date = (today - timedelta(days=cfg.edition.dedup_lookback_days)).strftime("%Y-%m-%d")
    recent = db.recent_selected_titles(conn, since_date)
    recent_titles = [title for title, _ in recent]
    recent_dedupe_keys = {key for _, key in recent if key}
    # History, not today's output — feeds the "Recently covered Margin lessons"/
    # avoid-french prompt sections (and the vocab hard backstop) so the Margin
    # band and Lexicon stop repeating across editions.
    recent_lessons = db.recent_lessons(conn, since_date)
    recent_french = db.recent_french_words(conn, since_date)

    pool = _candidate_pool(cfg, conn, hours, recent_dedupe_keys)
    if not pool:
        console.print("[red]No candidates fetched — nothing to build.[/red]")
        raise typer.Exit(1)

    # Computed before the editorial pass because it drives the rotating-lesson
    # topic selection; it's a non-mutating SELECT MAX(...)+1, safe to read early.
    edition_number = db.next_edition_number(conn)
    console.print(f"[dim]Editorial pass ({edition_kind}, {len(pool)} candidates)…[/dim]")
    result = editorial.select_and_summarize(
        pool,
        cfg,
        edition_kind,
        edition_number,
        recent_titles,
        recent_lessons=recent_lessons,
        recent_french=recent_french,
    )
    if not result.selections:
        console.print("[red]Editorial pass selected nothing — aborting.[/red]")
        raise typer.Exit(1)

    items_by_id = {i.id: i for i in pool}
    date_str = today.strftime("%Y-%m-%d")
    html = render_html(
        result,
        items_by_id,
        cfg,
        date_display=today.strftime("%A, %B %-d, %Y"),
        edition_number=edition_number,
        kind=edition_kind,
        weather=_fetch_weather(cfg),
        sports=_fetch_sports(cfg, today),
        shows=_fetch_shows(cfg, today),
        your_day=_fetch_calendar(cfg, today, tz),
    )

    out_dir = Path(cfg.delivery.archive)
    html_path = out_dir / f"{date_str}.html"
    pdf_path = out_dir / f"{date_str}.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html)
    engine = html_to_pdf(html, pdf_path)

    edition = Edition(
        id=f"ed-{date_str}",
        date=date_str,
        edition_number=edition_number,
        kind=edition_kind,
        status="final",
        item_ids=[s.item_id for s in result.selections],
        read_time_estimate_min=estimate_read_time_min(result),
        pdf_path=pdf_path,
    )
    if not dry_run:
        selected_items = [items_by_id[item_id] for item_id in edition.item_ids]
        db.mark_seen(conn, selected_items)
        db.save_edition(conn, edition, edition.item_ids)
        db.save_lessons_and_vocab(
            conn,
            edition.id,
            [(lesson.topic, lesson.title, lesson.body) for lesson in result.lessons],
            [(w.word, w.gloss) for w in result.french_vocab],
        )
    conn.close()

    console.print(
        f"\n[bold]Edition №{edition_number}[/bold] — “{escape(result.edition_headline)}”\n"
        f"{len(result.selections)} items · ~{edition.read_time_estimate_min} min read\n"
        f"PDF ({engine}): {pdf_path}\nHTML: {html_path}"
        + ("\n[yellow]Dry run — not archived, items not marked seen.[/yellow]" if dry_run else "")
    )


def _fetch_weather(cfg: StillConfig) -> Weather | None:
    w = cfg.almanac.weather
    if not w.enabled:
        return None
    with httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        return weather_mod.fetch(w.lat, w.lng, w.label, client)


def _fetch_sports(cfg: StillConfig, today: datetime) -> list[ScoreRow]:
    a = cfg.almanac
    if not any(t.enabled for t in a.teams) and not any(s.enabled for s in a.series):
        return []
    with httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        return sports_mod.fetch_sports(
            a.teams, a.series, client, Path("data/badges"), today=today.date()
        )


def _fetch_shows(cfg: StillConfig, today: datetime) -> list[ShowRow]:
    s = cfg.almanac.shows
    if not s.enabled or not s.artists:
        return []
    client_id = os.environ.get("SEATGEEK_CLIENT_ID")
    if not client_id:
        console.print(
            "[yellow]Upcoming Shows: set SEATGEEK_CLIENT_ID to enable the card "
            "(free key: https://seatgeek.com/account/develop).[/yellow]"
        )
        return []
    with httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        return shows_mod.fetch_shows(
            s.artists,
            client,
            lat=s.lat,
            lng=s.lng,
            range_mi=s.range_mi,
            today=today.date(),
            client_id=client_id,
            max_rows=s.max_rows,
        )


def _fetch_calendar(cfg: StillConfig, today: datetime, tz: ZoneInfo) -> YourDay | None:
    yd = cfg.almanac.your_day
    if not yd.enabled:
        return None
    if yd.weekdays_only and today.weekday() >= 5:
        return None  # weekend: no "first meeting" — stay quiet, don't nag about a token
    creds = calendar_mod.load_credentials(_calendar_token_path())
    if creds is None or not creds.token:
        console.print(
            "[yellow]Your Day: no Google Calendar token — run 'still calendar auth' "
            "to enable the masthead line.[/yellow]"
        )
        return None
    with httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        return calendar_mod.fetch(
            creds.token,
            client,
            today=today,
            tz=tz,
            weekdays_only=yd.weekdays_only,
            calendar_id=yd.calendar_id,
        )


def _resolve_kind(kind: str, today: datetime, cfg: StillConfig) -> editorial.EditionKind:
    if kind in ("weekday", "weekend"):
        return kind  # type: ignore[return-value]
    weekend_day = 5 if cfg.edition.weekend.day == "saturday" else 6
    return "weekend" if today.weekday() == weekend_day else "weekday"


def _candidate_pool(
    cfg: StillConfig,
    conn: sqlite3.Connection,
    hours: int,
    recent_dedupe_keys: set[str] | None = None,
) -> list[Item]:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    since = datetime.now(UTC) - timedelta(hours=hours)
    items: list[Item] = []
    with httpx.Client(
        timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        for source in cfg.sources:
            if not source.enabled:
                continue
            if isinstance(source, RssSource):
                fetched = rss.fetch(source, client, since)
            elif isinstance(source, HnAlgoliaSource):
                fetched = hn.fetch(source, client, since)
            elif isinstance(source, RedditSource):
                fetched = reddit.fetch(source, client)
            else:
                console.print(
                    f"[dim]{source.name}: skipped ({source.method} not implemented)[/dim]"
                )
                continue
            console.print(f"[dim]{source.name}: {len(fetched)} items[/dim]")
            items.extend(fetched)
    return rank(dedupe(items, db.seen_urls(conn), recent_dedupe_keys), cfg)


def _print_candidates(candidates: list[Item], cfg: StillConfig) -> None:
    now = datetime.now(UTC)
    console.print(
        f"\n[bold]Candidate pool[/bold] — {len(candidates)} items after dedupe. "
        "Quotas shown are the edition budget the editorial pass will enforce.\n"
    )
    for section in cfg.sections:
        section_items = [i for i in candidates if i.section == section.id]
        if not section_items:
            continue
        table = Table(
            title=f"{section.title} — {len(section_items)} candidates, quota {section.max_items}",
            title_justify="left",
        )
        table.add_column("Score", justify="right")
        table.add_column("Age", justify="right")
        table.add_column("Source")
        table.add_column("Title", overflow="fold")
        for item in section_items:
            age_h = int((now - item.published_at).total_seconds() // 3600)
            table.add_row(
                f"{item.score:.2f}" if item.score is not None else "—",
                f"{age_h}h",
                item.source_name,
                f"{escape(item.title)}\n[dim]{escape(item.canonical_url)}[/dim]",
            )
        console.print(table)
        console.print()
