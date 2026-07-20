"""Reddit adapter against a mocked public RSS feed — no network in tests."""

from xml.sax.saxutils import escape as xml_escape

import httpx

from still.config import RedditSource
from still.ingest import reddit


def make_source(**overrides: object) -> RedditSource:
    payload: dict[str, object] = {
        "name": "r/LocalLLaMA",
        "section": "ai",
        "method": "reddit",
        "class": "trusted",
        "subreddit": "LocalLLaMA",
        "max_items": 2,
    }
    payload.update(overrides)
    return RedditSource.model_validate(payload)


def client_returning(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: response))


def entry(
    *,
    title: str,
    permalink: str,
    link_href: str,
    comments_href: str,
    selftext: str | None = None,
    author: str = "some_user",
    published: str = "2026-07-19T08:52:53+00:00",
) -> str:
    body = (
        f'<!-- SC_OFF --><div class="md"><p>{selftext}</p></div><!-- SC_ON -->' if selftext else ""
    )
    raw_html = (
        f'<table> <tr><td> <a href="{permalink}">'
        f"<img /> </a> </td><td> {body} "
        f'submitted by <a href="https://www.reddit.com/user/{author}"> '
        f"/u/{author} </a> <br/> "
        f'<span><a href="{link_href}">[link]</a></span> '
        f'<span><a href="{comments_href}">[comments]</a></span> '
        "</td></tr></table>"
    )
    content = xml_escape(raw_html)
    return f"""  <entry>
    <author><name>/u/{author}</name></author>
    <content type="html">{content}</content>
    <id>t3_{permalink.rstrip("/").rsplit("/", 1)[-1]}</id>
    <link href="{permalink}" />
    <updated>{published}</updated>
    <published>{published}</published>
    <title>{title}</title>
  </entry>"""


def feed(*entries: str) -> str:
    body = "\n".join(entries)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>top scoring links : LocalLLaMA</title>
{body}
</feed>
"""


LINK_ENTRY = entry(
    title="A great local model release",
    permalink="https://www.reddit.com/r/LocalLLaMA/comments/abc/a_great_local_model_release/",
    link_href="https://huggingface.co/example/model?utm_source=reddit",
    comments_href="https://www.reddit.com/r/LocalLLaMA/comments/abc/a_great_local_model_release/",
    author="some_user",
)

SELF_ENTRY = entry(
    title="Discussion: best quant for 8B models &amp; friends",
    permalink="https://www.reddit.com/r/LocalLLaMA/comments/def/discussion/",
    link_href="https://www.reddit.com/r/LocalLLaMA/comments/def/discussion/",
    comments_href="https://www.reddit.com/r/LocalLLaMA/comments/def/discussion/",
    selftext="Body text &amp; more of the self post.",
    author="another_user",
)


def test_fetch_normalizes_link_and_self_posts() -> None:
    source = make_source(max_items=5)
    items = reddit.fetch(
        source, client_returning(httpx.Response(200, text=feed(LINK_ENTRY, SELF_ENTRY)))
    )

    assert len(items) == 2
    link, self_post = items
    assert link.title == "A great local model release"
    assert link.canonical_url == "https://huggingface.co/example/model"  # tracking param stripped
    assert link.author == "some_user"
    assert link.section == "ai"
    assert link.class_ == "trusted"
    assert link.source_name == "r/LocalLLaMA"
    assert link.raw_body is None  # not a self post

    assert self_post.title == "Discussion: best quant for 8B models & friends"
    assert self_post.canonical_url == "https://www.reddit.com/r/LocalLLaMA/comments/def/discussion"
    assert self_post.raw_body == "Body text & more of the self post."


def test_fetch_respects_max_items_cap() -> None:
    source = make_source(max_items=1)
    items = reddit.fetch(
        source, client_returning(httpx.Response(200, text=feed(LINK_ENTRY, SELF_ENTRY)))
    )

    assert len(items) == 1
    assert items[0].title == "A great local model release"


def test_fetch_requests_top_of_day_with_limit() -> None:
    source = make_source(max_items=3)

    def check_params(request: httpx.Request) -> httpx.Response:
        assert request.url.params["t"] == "day"
        assert request.url.params["limit"] == "3"
        assert request.url.path == "/r/LocalLLaMA/top/.rss"
        return httpx.Response(200, text=feed(LINK_ENTRY))

    client = httpx.Client(transport=httpx.MockTransport(check_params))
    reddit.fetch(source, client)


def test_fetch_returns_empty_on_http_error() -> None:
    source = make_source()
    items = reddit.fetch(source, client_returning(httpx.Response(404)))
    assert items == []


def test_fetch_returns_empty_on_unparseable_feed() -> None:
    source = make_source()
    items = reddit.fetch(source, client_returning(httpx.Response(200, text="not xml at all")))
    assert items == []
