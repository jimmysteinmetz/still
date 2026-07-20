"""Fixed two-page layout contract — the geometry the pipeline must obey.

The edition is ALWAYS exactly two pages (spec §2: the finite budget IS the
product, and a stable printed shape is part of the calm). Geometry is design,
not user configuration — `config/still.yaml` stays the product UI, while these
constants are the single tuning surface for the fixed layout, shared by
editorial enforcement (`enforce_budget` truncates text to WORD_CAPS and clamps
the selection to `capacity`) and rendering (`render_html` splits The Wire with
`split_wire`). Both sides MUST use the same split, which is why it lives here.

Page 1: masthead → lead-row (feature well + rail) → The Wire's front row
(P1_WIRE_SLOTS stories, one per column). Page 2: The Margin → the remaining
wire (up to P2_WIRE_SLOTS) → Lexicon pinned at the foot. Region heights live
in the template (edition.html.j2); slot counts and word caps live here so the
words can never outgrow the boxes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from still.pipeline.editorial import Selection

EditionKind = Literal["weekday", "weekend"]

# Stories on page 1 below the lead-row: one per Wire column.
P1_WIRE_SLOTS = 4
# Stories on page 2 between The Margin and the Lexicon. Weekday 13 is a
# measured fit: 14 worst-legal-case briefs need ~186mm of wire against the
# 182mm the .wire-p2-box can give without colliding with a full Lexicon —
# cut harder, never squeeze the type (spec §2). Weekend runs fewer,
# larger-set stories (3 columns at bigger type) so its page 2 still fills.
P2_WIRE_SLOTS: dict[EditionKind, int] = {"weekday": 13, "weekend": 5}

# Hard per-tier word ceilings, enforced by truncation in enforce_budget — the
# prompt targets sit just under these so machine truncation stays rare. Sized
# so a worst-legal-case story still fits its fixed box in the template.
WORD_CAPS: dict[EditionKind, dict[str, int]] = {
    "weekday": {
        "marquee": 200,
        "front": 95,
        "brief": 55,
        "deck": 24,
        "headline": 16,
        "theme": 20,
        "lesson": 60,
        "gloss": 22,
        "french": 15,
    },
    "weekend": {
        "marquee": 220,
        "front": 95,
        "brief": 45,
        "deck": 24,
        "headline": 16,
        "theme": 20,
        "lesson": 60,
        "gloss": 22,
        "french": 15,
    },
}


def capacity(kind: EditionKind) -> int:
    """The story ceiling the fixed layout can hold: marquee + front row + page 2.
    config max_items may ask for fewer, never more — enforce_budget clamps to it."""
    return 1 + P1_WIRE_SLOTS + P2_WIRE_SLOTS[kind]


def split_wire(
    selections: list[Selection], kind: EditionKind
) -> tuple[Selection | None, list[Selection], list[Selection]]:
    """Deterministically split a selection into (marquee, front, rest).

    marquee — the first "pressing" story, or (if a malfunctioning model flagged
    none) simply the first selection, so the front always has a lead.
    front — the page-1 Wire row: remaining "pressing" stories first (stable,
    model order within tiers), topped up to P1_WIRE_SLOTS with briefs.
    rest — everything else in model order; render groups it by section.
    """
    if not selections:
        return None, [], []
    marquee = next((s for s in selections if s.prominence == "pressing"), selections[0])
    remaining = [s for s in selections if s.item_id != marquee.item_id]
    front = sorted(remaining, key=lambda s: s.prominence != "pressing")[:P1_WIRE_SLOTS]
    front_ids = {s.item_id for s in front}
    rest = [s for s in remaining if s.item_id not in front_ids]
    return marquee, front, rest
