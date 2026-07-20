"""Fixed-layout contract: split_wire determinism and capacity arithmetic."""

from typing import Literal

from still.pipeline.editorial import Selection
from still.pipeline.layout import P1_WIRE_SLOTS, P2_WIRE_SLOTS, capacity, split_wire


def sel(n: int, prominence: Literal["pressing", "brief"] = "brief") -> Selection:
    return Selection(
        item_id=f"item{n}",
        section="ai",
        headline=f"H{n}",
        summary="S.",
        prominence=prominence,
    )


def test_capacity_matches_slot_arithmetic() -> None:
    assert capacity("weekday") == 1 + P1_WIRE_SLOTS + P2_WIRE_SLOTS["weekday"]
    assert capacity("weekend") == 1 + P1_WIRE_SLOTS + P2_WIRE_SLOTS["weekend"]
    # The geometry the product decisions were made against — a deliberate
    # tripwire: retuning slots means revisiting still.yaml's max_items too.
    assert capacity("weekday") == 18
    assert capacity("weekend") == 10


def test_empty_selection_is_safe() -> None:
    assert split_wire([], "weekday") == (None, [], [])


def test_marquee_is_first_pressing() -> None:
    sels = [sel(0), sel(1, "pressing"), sel(2, "pressing")]
    marquee, front, rest = split_wire(sels, "weekday")
    assert marquee is not None and marquee.item_id == "item1"
    assert marquee.item_id not in {s.item_id for s in front + rest}


def test_marquee_falls_back_to_first_selection() -> None:
    sels = [sel(0), sel(1), sel(2)]
    marquee, front, rest = split_wire(sels, "weekday")
    assert marquee is not None and marquee.item_id == "item0"


def test_front_leads_with_pressing_then_tops_up_in_model_order() -> None:
    # marquee = item1 (first pressing); front should lead with the other
    # pressing story (item4) then top up with briefs in model order.
    sels = [sel(0), sel(1, "pressing"), sel(2), sel(3), sel(4, "pressing"), sel(5), sel(6)]
    marquee, front, rest = split_wire(sels, "weekday")
    assert [s.item_id for s in front] == ["item4", "item0", "item2", "item3"]
    assert [s.item_id for s in rest] == ["item5", "item6"]


def test_front_never_exceeds_slots_and_rest_keeps_model_order() -> None:
    sels = [sel(n) for n in range(10)]
    marquee, front, rest = split_wire(sels, "weekday")
    assert len(front) == P1_WIRE_SLOTS
    assert [s.item_id for s in rest] == [f"item{n}" for n in range(5, 10)]


def test_short_edition_yields_partial_front_and_empty_rest() -> None:
    sels = [sel(0, "pressing"), sel(1), sel(2)]
    marquee, front, rest = split_wire(sels, "weekday")
    assert marquee is not None and marquee.item_id == "item0"
    assert [s.item_id for s in front] == ["item1", "item2"]
    assert rest == []


def test_split_is_deterministic() -> None:
    sels = [sel(n, "pressing" if n % 3 == 0 else "brief") for n in range(12)]
    assert split_wire(sels, "weekday") == split_wire(sels, "weekday")
