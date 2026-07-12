"""RSS/Atom adapter — preferred, cheapest, most stable method (spec §5.1)."""

import calendar
import logging
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from still.config import RssSource
from still.models import Item
from still.pipeline.normalize import canonicalize_url, make_item_id, title_key

logger = logging.getLogger(__name__)


def fetch(source: RssSource, client: httpx.Client, since: datetime) -> list[Item]:
    """Fetch and parse a feed; a dead source skips gracefully (spec §12)."""
    try:
        resp = client.get(source.url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("skipping %s: %s", source.name, e)
        return []

    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        logger.warning("skipping %s: unparseable feed (%s)", source.name, feed.bozo_exception)
        return []

    items = []
    for entry in feed.entries:
        published = _entry_datetime(entry)
        link = entry.get("link")
        if not link or not published or published < since:
            continue
        url = canonicalize_url(link)
        items.append(
            Item(
                id=make_item_id(url),
                source_name=source.name,
                title=entry.get("title", "(untitled)").strip(),
                canonical_url=url,
                author=entry.get("author"),
                published_at=published,
                raw_body=entry.get("summary"),
                class_=source.class_,
                section=source.section,
                dedupe_key=title_key(entry.get("title", url)),
            )
        )
    return items


def _entry_datetime(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    # feedparser's *_parsed fields are UTC struct_times
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
