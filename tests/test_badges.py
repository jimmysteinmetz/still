"""Badge pipeline — monochrome data-URIs, cached, graceful. No live network."""

import base64
import io
from collections.abc import Callable
from pathlib import Path

import httpx
from PIL import Image

from still.render import badges


def _png(color: tuple[int, int, int, int] = (200, 30, 30, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (20, 20), color).save(buf, format="PNG")
    return buf.getvalue()


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_outputs_grayscale_data_uri(tmp_path: Path) -> None:
    raw = _png()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=raw)

    uri = badges.to_mono_data_uri("https://x/badge.png", _client(handler), tmp_path)
    assert uri is not None and uri.startswith("data:image/png;base64,")
    assert seen == ["https://x/badge.png"]  # fetched the URL as given
    img = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert img.mode == "LA"  # grayscale + preserved alpha


def test_cache_hit_skips_network(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=_png())

    client = _client(handler)
    first = badges.to_mono_data_uri("https://x/b.png", client, tmp_path)
    second = badges.to_mono_data_uri("https://x/b.png", client, tmp_path)
    assert first == second
    assert calls["n"] == 1


def test_http_error_returns_none(tmp_path: Path) -> None:
    client = _client(lambda request: httpx.Response(404))
    assert badges.to_mono_data_uri("https://x/missing.png", client, tmp_path) is None


def test_empty_url_returns_none(tmp_path: Path) -> None:
    client = _client(lambda request: httpx.Response(500))
    assert badges.to_mono_data_uri("", client, tmp_path) is None
