"""Reddit adapter — top-of-day per curated subreddit (spec §5.3 Reddit recipe).

Fetches each subreddit's public `/top/.rss?t=day` Atom feed over plain https —
no OAuth app, no credentials. (Reddit closed self-service API app registration
in late 2025 under its Responsible Builder Policy; new OAuth apps now require
a manual approval ticket, so the old praw/OAuth path is gone. The RSS feed
needs no approval and already returns top-of-day ordering, which is the same
thing the old `top(time_filter="day")` call did.)

The feed has no upvote score, so there's no `min_upvotes` floor to apply
client-side any more — `top/.rss` is already sorted best-first, and
`max_items` caps how deep into that ordering a source reaches. A dead/private
subreddit just 404s and skips gracefully (spec §12), same as every other
source. Dedupe vs HN matters — that's the pipeline.dedupe stage's job, not
this adapter's.
"""

import calendar
import html
import logging
import re
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from still.config import RedditSource
from still.models import Item
from still.pipeline.normalize import canonicalize_url, make_item_id, title_key

logger = logging.getLogger(__name__)

# Reddit's RSS template wraps the external link and the comments permalink in
# fixed `[link]` / `[comments]` anchor spans — stable since old.reddit.com's
# RSS predates the API and plenty of tooling still relies on this exact shape.
_LINK_RE = re.compile(r'<a href="([^"]+)">\[link\]</a>')
_COMMENTS_RE = re.compile(r'<a href="([^"]+)">\[comments\]</a>')
_SELFTEXT_RE = re.compile(r"<!-- SC_OFF --><div class=\"md\">(.*)</div><!-- SC_ON -->", re.DOTALL)


def fetch(source: RedditSource, client: httpx.Client) -> list[Item]:
    """Top-of-day posts from one subreddit's public RSS feed."""
    url = f"https://www.reddit.com/r/{source.subreddit}/top/.rss"
    try:
        resp = client.get(url, params={"t": "day", "limit": source.max_items})
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("skipping %s: %s", source.name, e)
        return []

    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        logger.warning("skipping %s: unparseable feed (%s)", source.name, feed.bozo_exception)
        return []

    items = []
    for entry in feed.entries[: source.max_items]:
        title = entry.get("title", "(untitled)").strip()
        permalink = entry.get("link")
        published = _entry_datetime(entry)
        if not permalink or not published:
            continue

        content = entry.get("content", [{}])[0].get("value", "")
        link_match = _LINK_RE.search(content)
        comments_match = _COMMENTS_RE.search(content)
        external_url = link_match.group(1) if link_match else None
        comments_url = comments_match.group(1) if comments_match else permalink

        is_self = external_url is None or external_url == comments_url
        url_ = canonicalize_url(permalink if is_self else external_url)  # type: ignore[arg-type]

        raw_body = None
        if is_self:
            selftext_match = _SELFTEXT_RE.search(content)
            if selftext_match:
                raw_body = _strip_tags(selftext_match.group(1)).strip() or None

        author = entry.get("author")
        items.append(
            Item(
                id=make_item_id(url_),
                source_name=source.name,
                title=title,
                canonical_url=url_,
                author=author.removeprefix("/u/") if author else None,
                published_at=published,
                raw_body=raw_body,
                class_=source.class_,
                section=source.section,
                dedupe_key=title_key(title),
            )
        )
    return items


def _entry_datetime(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def _strip_tags(markup: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", markup))
