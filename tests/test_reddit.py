"""Reddit adapter against a fake praw client — no live network in tests."""

from dataclasses import dataclass
from typing import Any

import praw
import prawcore
import pytest

from still.config import RedditSource
from still.ingest import reddit


def make_source(**overrides: Any) -> RedditSource:
    payload: dict[str, Any] = {
        "name": "r/LocalLLaMA",
        "section": "ai",
        "method": "reddit",
        "class": "trusted",
        "subreddit": "LocalLLaMA",
        "min_upvotes": 100,
        "max_items": 2,
    }
    payload.update(overrides)
    return RedditSource.model_validate(payload)


@dataclass
class FakeRedditor:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass
class FakeSubmission:
    title: str
    score: int
    url: str
    permalink: str
    created_utc: float
    author: FakeRedditor | None = None
    is_self: bool = False
    selftext: str = ""


class FakeSubreddit:
    def __init__(self, posts: list[FakeSubmission]) -> None:
        self._posts = posts
        self.requested_limit: int | None = None
        self.requested_time_filter: str | None = None

    def top(self, *, time_filter: str = "all", limit: int | None = None) -> list[FakeSubmission]:
        self.requested_time_filter = time_filter
        self.requested_limit = limit
        return self._posts


class FakeReddit:
    def __init__(self, subreddit: FakeSubreddit) -> None:
        self._subreddit = subreddit

    def subreddit(self, name: str) -> FakeSubreddit:
        return self._subreddit


class ExplodingSubreddit:
    def top(self, *, time_filter: str = "all", limit: int | None = None) -> list[Any]:
        raise prawcore.exceptions.ResponseException(type("R", (), {"status_code": 503})())


class ExplodingReddit:
    def subreddit(self, name: str) -> ExplodingSubreddit:
        return ExplodingSubreddit()


POSTS = [
    FakeSubmission(
        title="A great local model release",
        score=250,
        url="https://huggingface.co/example/model?utm_source=reddit",
        permalink="/r/LocalLLaMA/comments/abc/a_great_local_model_release/",
        created_utc=1_750_000_000.0,
        author=FakeRedditor("some_user"),
    ),
    FakeSubmission(
        title="Discussion: best quant for 8B models",
        score=150,
        url="https://www.reddit.com/r/LocalLLaMA/comments/def/discussion/",
        permalink="/r/LocalLLaMA/comments/def/discussion_best_quant_for_8b_models/",
        created_utc=1_750_001_000.0,
        author=FakeRedditor("another_user"),
        is_self=True,
        selftext="Body text of the self post.",
    ),
    FakeSubmission(
        title="A low-effort meme",
        score=10,  # below min_upvotes
        url="https://i.redd.it/meme.png",
        permalink="/r/LocalLLaMA/comments/ghi/meme/",
        created_utc=1_750_002_000.0,
        author=None,
    ),
]


def test_fetch_normalizes_posts_and_filters_by_upvotes() -> None:
    source = make_source(max_items=5)
    fake = FakeReddit(FakeSubreddit(POSTS))

    items = reddit.fetch(source, fake)  # type: ignore[arg-type]

    assert len(items) == 2  # the 10-upvote meme is filtered out
    link, self_post = items
    assert link.title == "A great local model release"
    assert link.canonical_url == "https://huggingface.co/example/model"  # tracking param stripped
    assert link.author == "some_user"
    assert link.section == "ai"
    assert link.class_ == "trusted"
    assert link.source_name == "r/LocalLLaMA"
    assert link.raw_body is None  # not a self post

    assert self_post.title == "Discussion: best quant for 8B models"
    assert (
        self_post.canonical_url
        == "https://www.reddit.com/r/LocalLLaMA/comments/def/discussion_best_quant_for_8b_models"
    )
    assert self_post.raw_body == "Body text of the self post."


def test_fetch_respects_max_items_cap() -> None:
    source = make_source(max_items=1)
    fake = FakeReddit(FakeSubreddit(POSTS))

    items = reddit.fetch(source, fake)  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].title == "A great local model release"


def test_build_client_returns_none_without_credentials() -> None:
    assert reddit.build_client(None, "secret") is None
    assert reddit.build_client("id", None) is None
    assert reddit.build_client(None, None) is None


def test_fetch_returns_empty_when_client_is_none() -> None:
    """Missing creds → build_client(...) is None → source skipped, never raises."""
    source = make_source()
    assert reddit.fetch(source, None) == []


def test_fetch_returns_empty_on_api_exception() -> None:
    source = make_source()

    items = reddit.fetch(source, ExplodingReddit())  # type: ignore[arg-type]

    assert items == []


def test_build_client_constructs_read_only_client_with_credentials() -> None:
    client = reddit.build_client("test-id", "test-secret", user_agent="still-tests/0.1")
    assert isinstance(client, praw.Reddit)


def test_build_client_handles_construction_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise prawcore.exceptions.OAuthException(
            type("R", (), {"status_code": 401})(), error="invalid_grant"
        )

    monkeypatch.setattr(praw, "Reddit", boom)
    assert reddit.build_client("bad-id", "bad-secret") is None
