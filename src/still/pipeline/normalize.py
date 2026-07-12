"""NORMALIZE stage (spec §7): canonical URLs, stable ids, dedupe keys.

Canonical URLs make cross-source dedupe work: HN, Reddit, and feeds often
link the same story with different tracking params or trailing slashes.
"""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "source"}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_") and k not in TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def make_item_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode()).hexdigest()[:16]


def title_key(title: str) -> str:
    """Normalized title for same-story-different-url dedupe."""
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
