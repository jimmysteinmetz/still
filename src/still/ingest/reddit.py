"""Reddit adapter — top-of-day per curated subreddit (spec §5.3 Reddit recipe).

One `top(time_filter="day")` call per subreddit via praw (OAuth "script" app,
read-only), upvote threshold from config. Credentials come from env vars
(REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET/REDDIT_USER_AGENT, same
gitignored-`.env`-or-Secret-Manager pattern as SEATGEEK_CLIENT_ID) — missing
creds just hide reddit sources, never break the build. Dedupe vs HN matters —
that's the pipeline.dedupe stage's job, not this adapter's.
"""

import logging
from datetime import UTC, datetime

import praw
import prawcore

from still.config import RedditSource
from still.models import Item
from still.pipeline.normalize import canonicalize_url, make_item_id, title_key

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "still:personal-newspaper:v0.1 (by /u/still-bot)"


def build_client(
    client_id: str | None,
    client_secret: str | None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> praw.Reddit | None:
    """Build a read-only praw client, or None if credentials are missing.

    Read-only (script-app client_id/secret, no username/password) needs no
    interactive auth — the app just needs to exist at reddit.com/prefs/apps.
    """
    if not client_id or not client_secret:
        logger.warning(
            "reddit: missing REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET — reddit sources skipped"
        )
        return None
    try:
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            check_for_updates=False,
        )
    except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException) as e:
        logger.warning("reddit: failed to build client: %s", e)
        return None


def fetch(source: RedditSource, reddit: praw.Reddit | None) -> list[Item]:
    """Top-of-day posts from one subreddit above the configured upvote floor."""
    if reddit is None:
        return []
    items: list[Item] = []
    try:
        # Over-fetch a bit since min_upvotes filters client-side (top() isn't
        # pre-filterable by score) — capped well below the source's max_items
        # blowing up into a huge listing pull.
        submissions = reddit.subreddit(source.subreddit).top(
            time_filter="day", limit=source.max_items * 5
        )
        for post in submissions:
            if post.score < source.min_upvotes:
                continue
            title = str(post.title).strip()
            if post.is_self:
                url = canonicalize_url(f"https://www.reddit.com{post.permalink}")
            else:
                url = canonicalize_url(str(post.url))
            items.append(
                Item(
                    id=make_item_id(url),
                    source_name=source.name,
                    title=title,
                    canonical_url=url,
                    author=str(post.author) if post.author else None,
                    published_at=datetime.fromtimestamp(post.created_utc, tz=UTC),
                    raw_body=str(post.selftext) if post.is_self and post.selftext else None,
                    class_=source.class_,
                    section=source.section,
                    dedupe_key=title_key(title),
                )
            )
            if len(items) >= source.max_items:
                break
    except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException) as e:
        logger.warning("skipping %s: %s", source.name, e)
        return []
    return items
