"""Beta 4 field reports (hass-anycubic-next ACCEPTANCE D21-D22)."""

from __future__ import annotations

from typing import Any

import pytest

from anycubic_lan.reports import AceBox, PrinterState, parse_message

from .payloads import ACE_BOX, message


def apply(state: PrinterState, *payloads: Any) -> PrinterState:
    for payload in payloads:
        report = parse_message(payload)
        assert report is not None
        state = state.apply(report)
    return state


def boxes(*data: dict[str, Any], action: str = "getInfo") -> dict[str, Any]:
    return message(
        "multiColorBox",
        {"multi_color_box": list(data)},
        action=action,
        state="success",
    )


# -- D22: an ACE's own humidity -------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "humidity"),
    [(58, 58), (84.5, 84.5), (0, 0), (0.0, 0), (None, None)],
)
def test_box_humidity_is_read(raw: object, humidity: float | None) -> None:
    box = AceBox.from_data(ACE_BOX | {"humidity": raw})
    assert box.humidity == humidity


def test_box_without_humidity_reads_none() -> None:
    assert AceBox.from_data(ACE_BOX).humidity is None


def test_box_humidity_of_two_boxes_and_a_partial_report() -> None:
    state = apply(
        PrinterState(),
        boxes(ACE_BOX | {"humidity": 61}, ACE_BOX | {"id": 1, "humidity": 0}),
    )
    assert [b.humidity for b in state.ace_boxes] == [61, 0]
    # A partial report without the field keeps the reading; one with it updates.
    state = apply(
        state,
        message("multiColorBox", {"id": 0, "temp": 30}, action="autoUpdateInfo"),
    )
    assert state.ace_boxes[0].humidity == 61
    state = apply(
        state,
        message("multiColorBox", {"id": 1, "humidity": 77}, action="autoUpdateInfo"),
    )
    assert [b.humidity for b in state.ace_boxes] == [61, 77]


# -- D21: chamber temperature (already read since 0.1.0) ------------------------


def test_chamber_temperature_from_info_and_tempature() -> None:
    temps = {"curr_hotbed_temp": 60, "curr_nozzle_temp": 220}
    state = apply(
        PrinterState(), message("tempature", temps | {"curr_chamber_temp": 0})
    )
    assert state.temperatures.chamber == 0
    assert not state.has_chamber
    state = apply(state, message("tempature", temps | {"curr_chamber_temp": 32}))
    assert state.temperatures.chamber == 32
    assert state.has_chamber
