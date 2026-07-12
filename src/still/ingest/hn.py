"""Hacker News adapter via Algolia search_by_date (spec §5.3 HN recipe).

One call: stories from the lookback window above the configured points bar.

Algolia's HN index no longer has `points` configured as a filterable numeric
attribute — a `numericFilters` clause referencing it 400s unconditionally
("invalid numeric attribute(points)..."). So the points bar is applied
client-side on the parsed hits instead of server-side. That means the
`created_at_i`-only query is no longer pre-filtered to just the popular
stories, so `hitsPerPage` is raised to Algolia's practical max (1000, the
observed hard cap regardless of a higher requested value) to cover most of
the day's volume (~1100-1200 HN stories/day) rather than just the 50 most
recent submissions, which would almost all still be at 0-2 points.
"""

import logging
from datetime import UTC, datetime

import httpx

from still.config import HnAlgoliaSource
from still.models import Item
from still.pipeline.normalize import canonicalize_url, make_item_id, title_key

logger = logging.getLogger(__name__)

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"


def fetch(source: HnAlgoliaSource, client: httpx.Client, since: datetime) -> list[Item]:
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{int(since.timestamp())}",
        "hitsPerPage": "1000",
    }
    try:
        resp = client.get(ALGOLIA_URL, params=params)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("skipping %s: %s", source.name, e)
        return []

    items = []
    for hit in resp.json().get("hits", []):
        if hit.get("points", 0) <= source.min_points:
            continue
        # Ask HN / Show HN posts have no external url; link to the discussion
        url = canonicalize_url(
            hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        )
        items.append(
            Item(
                id=make_item_id(url),
                source_name=source.name,
                title=hit.get("title", "(untitled)").strip(),
                canonical_url=url,
                author=hit.get("author"),
                published_at=datetime.fromtimestamp(hit["created_at_i"], tz=UTC),
                class_=source.class_,
                section=source.section,
                dedupe_key=title_key(hit.get("title", url)),
            )
        )
    return items
