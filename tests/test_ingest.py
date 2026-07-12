"""RSS and HN adapters against mocked HTTP — no network in tests."""

from datetime import UTC, datetime, timedelta

import httpx

from still.config import HnAlgoliaSource, RssSource
from still.ingest import hn, rss

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
SINCE = NOW - timedelta(hours=24)

ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Blog</title>
  <entry>
    <title>Fresh post about LLMs</title>
    <link href="https://blog.example.com/fresh/?utm_source=feed"/>
    <id>tag:blog.example.com,2026:fresh</id>
    <updated>2026-06-10T09:00:00Z</updated>
    <summary>Body text.</summary>
  </entry>
  <entry>
    <title>Stale post</title>
    <link href="https://blog.example.com/stale"/>
    <id>tag:blog.example.com,2026:stale</id>
    <updated>2026-06-01T09:00:00Z</updated>
  </entry>
</feed>
"""

HN_RESPONSE = {
    "hits": [
        {
            "objectID": "101",
            "title": "A big launch",
            "url": "https://startup.example.com/launch?utm_campaign=hn",
            "author": "pg",
            "created_at_i": int((NOW - timedelta(hours=3)).timestamp()),
            "points": 250,
        },
        {
            "objectID": "102",
            "title": "Ask HN: What are you working on?",
            "url": None,
            "author": "dang",
            "created_at_i": int((NOW - timedelta(hours=5)).timestamp()),
            "points": 150,
        },
    ]
}


def client_returning(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: response))


def test_rss_fetch_parses_and_filters_by_window() -> None:
    source = RssSource.model_validate(
        {
            "name": "Test Blog",
            "section": "ai",
            "method": "rss",
            "url": "https://blog.example.com/feed",
            "class": "trusted",
            "max_items": 3,
        }
    )
    items = rss.fetch(source, client_returning(httpx.Response(200, text=ATOM_FEED)), SINCE)
    assert len(items) == 1
    item = items[0]
    assert item.title == "Fresh post about LLMs"
    assert item.canonical_url == "https://blog.example.com/fresh"  # tracking + slash stripped
    assert item.class_ == "trusted"
    assert item.section == "ai"
    assert item.raw_body == "Body text."


def test_rss_fetch_skips_dead_source() -> None:
    source = RssSource.model_validate(
        {
            "name": "Dead Blog",
            "section": "ai",
            "method": "rss",
            "url": "https://gone.example.com/feed",
            "class": "trusted",
            "max_items": 1,
        }
    )
    items = rss.fetch(source, client_returning(httpx.Response(404)), SINCE)
    assert items == []


def test_hn_fetch_maps_hits_and_falls_back_to_discussion_url() -> None:
    source = HnAlgoliaSource.model_validate(
        {
            "name": "Hacker News",
            "section": "eng",
            "method": "hn_algolia",
            "class": "firehose",
            "min_points": 100,
            "max_items": 4,
        }
    )
    items = hn.fetch(source, client_returning(httpx.Response(200, json=HN_RESPONSE)), SINCE)
    assert len(items) == 2
    assert items[0].canonical_url == "https://startup.example.com/launch"
    assert items[1].canonical_url == "https://news.ycombinator.com/item?id=102"
    assert all(i.class_ == "firehose" for i in items)


def test_hn_fetch_does_not_filter_points_server_side() -> None:
    """Algolia 400s if numericFilters references points (index no longer allows it)."""
    source = HnAlgoliaSource.model_validate(
        {
            "name": "Hacker News",
            "section": "eng",
            "method": "hn_algolia",
            "class": "firehose",
            "min_points": 100,
            "max_items": 4,
        }
    )

    def check_no_points_filter(request: httpx.Request) -> httpx.Response:
        assert "points" not in request.url.params.get("numericFilters", "")
        return httpx.Response(200, json=HN_RESPONSE)

    client = httpx.Client(transport=httpx.MockTransport(check_no_points_filter))
    hn.fetch(source, client, SINCE)


def test_hn_fetch_filters_points_client_side() -> None:
    response = {
        "hits": [
            *HN_RESPONSE["hits"],
            {
                "objectID": "103",
                "title": "A quiet post",
                "url": "https://quiet.example.com/post",
                "author": "nobody",
                "created_at_i": int((NOW - timedelta(hours=2)).timestamp()),
                "points": 50,
            },
        ]
    }
    source = HnAlgoliaSource.model_validate(
        {
            "name": "Hacker News",
            "section": "eng",
            "method": "hn_algolia",
            "class": "firehose",
            "min_points": 100,
            "max_items": 4,
        }
    )
    items = hn.fetch(source, client_returning(httpx.Response(200, json=response)), SINCE)
    assert len(items) == 2
    assert all(i.canonical_url != "https://quiet.example.com/post" for i in items)
