"""SQLite persistence: seen-item history (cross-day dedupe) and edition archive."""

import sqlite3
from pathlib import Path

from still.models import Edition, Item

DEFAULT_DB_PATH = Path("data/still.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,
    source_name   TEXT NOT NULL,
    title         TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    dedupe_key    TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    edition_id    TEXT REFERENCES editions(id)
);
CREATE INDEX IF NOT EXISTS idx_items_dedupe ON items(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_items_url ON items(canonical_url);

CREATE TABLE IF NOT EXISTS editions (
    id             TEXT PRIMARY KEY,
    date           TEXT NOT NULL UNIQUE,
    edition_number INTEGER NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('weekday', 'weekend')),
    status         TEXT NOT NULL CHECK (status IN ('draft', 'final')),
    read_time_min  INTEGER,
    pdf_path       TEXT,
    archived_at    TEXT
);
"""


def connect(path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the database, creating the schema on first use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def next_edition_number(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(edition_number), 0) + 1 FROM editions").fetchone()
    return int(row[0])


def save_edition(conn: sqlite3.Connection, edition: Edition, selected_ids: list[str]) -> None:
    """Record a final edition and tag its items. Editions are immutable (spec §2.6)."""
    conn.execute(
        "INSERT INTO editions"
        " (id, date, edition_number, kind, status, read_time_min, pdf_path, archived_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (
            edition.id,
            edition.date,
            edition.edition_number,
            edition.kind,
            "final",
            edition.read_time_estimate_min,
            str(edition.pdf_path) if edition.pdf_path else None,
        ),
    )
    conn.executemany(
        "UPDATE items SET edition_id = ? WHERE id = ?",
        [(edition.id, item_id) for item_id in selected_ids],
    )
    conn.commit()


def seen_urls(conn: sqlite3.Connection) -> set[str]:
    """Canonical URLs already surfaced in past runs."""
    return {row[0] for row in conn.execute("SELECT canonical_url FROM items")}


def recent_selected_titles(
    conn: sqlite3.Connection, since_date: str
) -> list[tuple[str, str | None]]:
    """(title, dedupe_key) of items actually selected into a final edition on or
    after `since_date` (YYYY-MM-DD, inclusive) — cross-day topic dedup (TASK-3)."""
    return [
        (row[0], row[1])
        for row in conn.execute(
            "SELECT items.title, items.dedupe_key FROM items"
            " JOIN editions ON items.edition_id = editions.id"
            " WHERE editions.date >= ?"
            " ORDER BY editions.date DESC, items.title",
            (since_date,),
        )
    ]


def mark_seen(conn: sqlite3.Connection, items: list[Item]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO items"
        " (id, source_name, title, canonical_url, published_at, dedupe_key)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                i.id,
                i.source_name,
                i.title,
                i.canonical_url,
                i.published_at.isoformat(),
                i.dedupe_key,
            )
            for i in items
        ],
    )
    conn.commit()
