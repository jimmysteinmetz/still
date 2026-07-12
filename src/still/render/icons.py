"""Tiny monochrome weather icons as inline SVG.

Each icon is line-art on a 24×24 grid: `stroke="currentColor"` makes it inherit
the surrounding ink color, and being vector it stays crisp at any size with zero
image files. The renderer drops the matching string straight into the HTML.

Keys match weather.fetch()'s icon buckets. To add one: draw paths on the 24×24
grid and add an entry. `fill="none"` everywhere keeps it engraving-like; a
zero-length line with round caps (stroke-linecap) renders as a dot (see snow).
"""

_ATTRS = (
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"'
)

_CLOUD = "M7 17h9a3.5 3.5 0 0 0 .3-7 5 5 0 0 0-9.5-1.3A3.6 3.6 0 0 0 7 17z"

WEATHER_ICONS: dict[str, str] = {
    "clear": (
        f'<svg class="wx" {_ATTRS}>'
        '<circle cx="12" cy="12" r="4.2"/>'
        '<path d="M12 2.5v2.3M12 19.2v2.3M2.5 12h2.3M19.2 12h2.3'
        'M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6"/>'
        "</svg>"
    ),
    "partly": (
        f'<svg class="wx" {_ATTRS}>'
        '<circle cx="9" cy="9" r="3.1"/>'
        '<path d="M9 2.6v1.7M2.6 9h1.7M4.3 4.3l1.2 1.2M13.7 4.3l-1.2 1.2"/>'
        f'<path d="{_CLOUD}" fill="#fff"/>'
        "</svg>"
    ),
    "cloudy": f'<svg class="wx" {_ATTRS}><path d="{_CLOUD}"/></svg>',
    "fog": (f'<svg class="wx" {_ATTRS}><path d="M4 8h16M3 12h18M5 16h14M7 20h10"/></svg>'),
    "rain": (
        f'<svg class="wx" {_ATTRS}>'
        f'<path d="{_CLOUD}"/>'
        '<path d="M9 19l-1 2.4M13 19l-1 2.4M17 19l-1 2.4"/>'
        "</svg>"
    ),
    "snow": (
        f'<svg class="wx" {_ATTRS}>'
        f'<path d="{_CLOUD}"/>'
        '<path stroke-width="2.4" d="M9 20.2h0M13 21h0M16.5 20h0"/>'
        "</svg>"
    ),
    "storm": (
        f'<svg class="wx" {_ATTRS}><path d="{_CLOUD}"/><path d="M12 17l-2.2 3.6h3L11 24"/></svg>'
    ),
}


def weather_icon(key: str) -> str:
    """SVG markup for an icon key, falling back to a cloud."""
    return WEATHER_ICONS.get(key, WEATHER_ICONS["cloudy"])
