"""Normalize, dedupe, and rank — the pure pipeline stages."""

from datetime import UTC, datetime, timedelta

from still.config import load_config
from still.models import Item
from still.pipeline.dedupe import dedupe
from still.pipeline.normalize import canonicalize_url, make_item_id, title_key
from still.pipeline.rank import rank

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def make_item(**overrides: object) -> Item:
    defaults: dict = {
        "id": "x",
        "source_name": "Test",
        "title": "A story",
        "canonical_url": "https://example.com/a",
        "published_at": NOW - timedelta(hours=2),
        "class_": "trusted",
        "section": "ai",
    }
    defaults.update(overrides)
    defaults["dedupe_key"] = title_key(str(defaults["title"]))
    defaults["id"] = make_item_id(str(defaults["canonical_url"]))
    return Item(**defaults)


class TestNormalize:
    def test_strips_tracking_params_fragment_and_trailing_slash(self) -> None:
        url = "https://Example.com/Post/?utm_source=rss&utm_medium=feed&fbclid=abc#section"
        assert canonicalize_url(url) == "https://example.com/Post"

    def test_keeps_meaningful_query(self) -> None:
        url = "https://news.ycombinator.com/item?id=123"
        assert canonicalize_url(url) == "https://news.ycombinator.com/item?id=123"

    def test_title_key_normalizes(self) -> None:
        assert title_key("Show HN: Foo-Bar 2.0!") == title_key("show hn foobar 20")


class TestDedupe:
    def test_same_url_keeps_trusted_over_firehose(self) -> None:
        trusted = make_item(source_name="Blog", class_="trusted")
        firehose = make_item(source_name="HN", class_="firehose")
        kept = dedupe([firehose, trusted], seen_urls=set())
        assert len(kept) == 1
        assert kept[0].source_name == "Blog"

    def test_same_title_different_url_collapses(self) -> None:
        a = make_item(canonical_url="https://example.com/a")
        b = make_item(canonical_url="https://mirror.example.com/b")
        assert len(dedupe([a, b], seen_urls=set())) == 1

    def test_previously_seen_url_dropped(self) -> None:
        item = make_item()
        assert dedupe([item], seen_urls={item.canonical_url}) == []

    def test_distinct_stories_survive(self) -> None:
        a = make_item(title="Story one", canonical_url="https://example.com/1")
        b = make_item(title="Story two", canonical_url="https://example.com/2")
        assert len(dedupe([a, b], seen_urls=set())) == 2

    def test_recent_dedupe_key_blocks_reselection_across_days(self) -> None:
        # Different URL, same underlying story, no URL-level history — only the
        # cross-day title-key backstop can catch this (TASK-3).
        item = make_item(
            title="Simon Willison SQLite tools",
            canonical_url="https://mirror.example.com/sqlite-tools",
        )
        recent_dedupe_keys = {title_key("Simon Willison SQLite tools")}
        kept = dedupe([item], seen_urls=set(), recent_dedupe_keys=recent_dedupe_keys)
        assert kept == []


class TestRank:
    def test_interest_match_outranks_non_match(self) -> None:
        cfg = load_config()
        matched = make_item(title="Gemini LLM evals in production", class_="firehose")
        unmatched = make_item(
            title="Quarterly earnings recap",
            class_="firehose",
            canonical_url="https://example.com/other",
        )
        ranked = rank([unmatched, matched], cfg, now=NOW)
        assert ranked[0].title.startswith("Gemini")
        assert all(i.score is not None for i in ranked)

    def test_newer_outranks_older_same_source(self) -> None:
        cfg = load_config()
        fresh = make_item(published_at=NOW - timedelta(hours=1))
        stale = make_item(
            published_at=NOW - timedelta(hours=20),
            canonical_url="https://example.com/old",
            title="A story but older",
        )
        ranked = rank([stale, fresh], cfg, now=NOW)
        assert ranked[0].canonical_url == "https://example.com/a"
