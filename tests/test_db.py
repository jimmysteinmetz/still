"""SQLite persistence — seen-history, cross-day dedup, and edition archive."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from still import db
from still.models import Edition, Item

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def make_item(n: int, title: str | None = None, dedupe_key: str | None = None) -> Item:
    return Item(
        id=f"item{n}",
        source_name="Test",
        title=title or f"Story {n}",
        canonical_url=f"https://example.com/{n}",
        published_at=NOW - timedelta(hours=2),
        class_="firehose",
        section="ai",
        dedupe_key=dedupe_key if dedupe_key is not None else f"story {n}",
    )


def make_edition(edition_id: str, date: str, item_ids: list[str]) -> Edition:
    return Edition(
        id=edition_id,
        date=date,
        edition_number=1,
        kind="weekday",
        status="final",
        item_ids=item_ids,
    )


def test_recent_selected_titles_empty_when_no_editions(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "test.db")
    assert db.recent_selected_titles(conn, "2026-01-01") == []


def test_recent_selected_titles_returns_selected_only(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "test.db")
    selected = make_item(1, title="Selected story")
    rejected = make_item(2, title="Rejected story")
    db.mark_seen(conn, [selected, rejected])
    db.save_edition(conn, make_edition("ed-1", "2026-06-10", ["item1"]), ["item1"])

    result = db.recent_selected_titles(conn, "2026-01-01")

    assert result == [("Selected story", "story 1")]


def test_recent_selected_titles_respects_since_date(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "test.db")
    older = make_item(1, title="Old story")
    newer = make_item(2, title="New story")
    db.mark_seen(conn, [older, newer])
    db.save_edition(conn, make_edition("ed-1", "2026-06-01", ["item1"]), ["item1"])
    db.save_edition(conn, make_edition("ed-2", "2026-07-08", ["item2"]), ["item2"])

    result = db.recent_selected_titles(conn, "2026-07-01")

    assert result == [("New story", "story 2")]


def test_mark_seen_inserts_only_given_items(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "test.db")
    db.mark_seen(conn, [make_item(1)])
    assert db.seen_urls(conn) == {"https://example.com/1"}
