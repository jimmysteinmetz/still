"""Core pipeline schemas: Item and Edition (spec §9).

Every ingest adapter normalizes into Item; the pipeline stages enrich it
(score, summary, section) and an Edition is the immutable final selection.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from still.config import SourceClass


class Item(BaseModel):
    """One candidate story, normalized from any source."""

    id: str  # stable hash of canonical_url (or source+title fallback)
    source_name: str
    title: str
    canonical_url: str
    author: str | None = None
    published_at: datetime
    raw_body: str | None = None
    extracted_text: str | None = None
    class_: SourceClass
    section: str  # section id from config; editorial pass may reassign
    score: float | None = None  # set by rank stage
    summary: str | None = None  # set by editorial LLM pass
    dedupe_key: str | None = None


class Edition(BaseModel):
    """One day's finished newspaper. Immutable once status is 'final'."""

    id: str
    date: str  # YYYY-MM-DD
    edition_number: int
    kind: Literal["weekday", "weekend"]
    status: Literal["draft", "final"] = "draft"
    item_ids: list[str] = []
    read_time_estimate_min: int | None = None
    pdf_path: Path | None = None
    archived_at: datetime | None = None
