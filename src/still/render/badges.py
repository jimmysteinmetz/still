"""Team crests as monochrome base64 data-URIs (spec §4A Scoreboard).

ESPN serves color team logos (500px PNGs); the broadsheet is monochrome line-art, so
each crest is downsized then grayscaled + autocontrasted into an engraving-like glyph.
The conversion is baked into the image *bytes* on purpose: WeasyPrint (our primary PDF
engine) ignores CSS `filter`, so a CSS grayscale would silently no-op there.

Crests are inlined as data-URIs (not remote ``<img>``) so an archived edition stays
self-contained and never rots when a logo URL later moves (editions are immutable).
Processed results are cached on disk keyed by URL, so daily builds skip the network.
"""

import base64
import hashlib
import io
import logging
from pathlib import Path

import httpx
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


_MAX_PX = 96  # crests render ~12pt; 96px keeps them crisp without bloating the HTML


def _process(raw: bytes) -> str:
    """Downsize + grayscale + autocontrast a logo PNG, keeping transparency, → data-URI."""
    with Image.open(io.BytesIO(raw)) as img:
        rgba = img.convert("RGBA")
        rgba.thumbnail((_MAX_PX, _MAX_PX))
        alpha = rgba.getchannel("A")
        gray = ImageOps.autocontrast(ImageOps.grayscale(rgba.convert("RGB")))
        mono = Image.merge("LA", (gray, alpha))
        buf = io.BytesIO()
        mono.save(buf, format="PNG", optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def to_mono_data_uri(url: str, client: httpx.Client, cache_dir: Path) -> str | None:
    """Monochrome data-URI for a logo URL, cached on disk. None on any failure."""
    if not url:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()
    cache = cache_dir / f"{key}.txt"
    if cache.exists():
        return cache.read_text()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        uri = _process(resp.content)
    except (httpx.HTTPError, OSError, ValueError) as e:
        logger.warning("badge unavailable (%s): %s", url, e)
        return None
    cache.write_text(uri)
    return uri
