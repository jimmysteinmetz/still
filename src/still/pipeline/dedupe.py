"""DEDUPE stage (spec §7): cross-source and cross-day dedupe.

Reddit/HN/feeds overlap heavily (spec §5.3). Within a pool, the same story
(by canonical URL or normalized title) keeps one representative — trusted
sources win over firehoses, then earlier publication. Items already shown
in past editions (SQLite history) are dropped entirely.
"""

from still.models import Item


def dedupe(
    items: list[Item],
    seen_urls: set[str],
    recent_dedupe_keys: set[str] | None = None,
) -> list[Item]:
    kept: list[Item] = []
    urls: set[str] = set()
    titles: set[str] = set(recent_dedupe_keys or ())
    for item in sorted(items, key=lambda i: (i.class_ != "trusted", i.published_at)):
        if item.canonical_url in seen_urls or item.canonical_url in urls:
            continue
        if item.dedupe_key and item.dedupe_key in titles:
            continue
        urls.add(item.canonical_url)
        if item.dedupe_key:
            titles.add(item.dedupe_key)
        kept.append(item)
    return kept
