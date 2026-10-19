"""Beta 3 field reports (hass-anycubic-next ACCEPTANCE D10, D11, D13-D15)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from anycubic_lan import (
    ExternalFilamentBoxReport,
    FeedSource,
    FilamentFeed,
    PrintReport,
    current_filament,
    filament_feed,
)
from anycubic_lan.reports import Job, PrinterState, parse_message

from .payloads import ACE_BOX, PROJECT, info_with, message, project_with


def apply(state: PrinterState, *payloads: Any) -> PrinterState:
    for payload in payloads:
        report = parse_message(payload)
        assert report is not None
        state = state.apply(report)
    return state


def step(state: str, **data: Any) -> dict[str, Any]:
    """A filament-change ``print`` report as a Kobra X sends it (D10)."""
    return message("print", data, action="start", state=state, code=200)


# -- D15: job numbers as text, and -1 ------------------------------------------


@pytest.mark.parametrize(
    ("raw", "task_id", "job_id"),
    [
        ("-1", -1, None),
        (-1, -1, None),
        ("131189709", 131189709, 131189709),
        (131189709, 131189709, 131189709),
        (" 42 ", 42, 42),
        ("0", 0, None),
        (0, 0, None),
        (1.0, 1, 1),
        ("1.5", None, None),
        (1.5, None, None),
        ("abc", None, None),
        ("", None, None),
        (True, None, None),
        (None, None, None),
    ],
)
def test_job_number_as_text_or_number(raw: object, task_id: Any, job_id: Any) -> None:
    for key in ("task_id", "taskid"):
        job = Job.from_data({key: raw})
        assert job.task_id == task_id
        assert job.job_id == job_id


def test_kobra_4_lan_print_numbers() -> None:
    last = {
        "task_id": "131189709",
        "localtask": "abc",
        "state": "finished",
        "print_status": 2,
    }
    state = apply(
        PrinterState(),
        info_with(state="busy", project=project_with(task_id="-1"), last_project=last),
    )
    assert state.job is not None
    assert state.job.task_id == -1
    assert state.job.job_id is None
    assert state.last_job is not None
    assert state.last_job.job_id == 131189709
    # The start report numbers the job "-1" too and is the same job.
    state = apply(
        state,
        message(
            "print", {"taskid": "-1", "progress": 70}, action="start", state="printing"
        ),
    )
    assert state.job is not None
    assert state.job.progress == 70
    assert state.job.filename == PROJECT["filename"]


def test_print_start_report_numbered_minus_one_starts_the_job() -> None:
    start = message(
        "print",
        {"taskid": "-1", "filename": "a.gcode", "print_status": 1},
        action="start",
        state="printing",
    )
    state = apply(PrinterState(), info_with(state="busy"), start)
    assert state.job is not None
    assert state.job.task_id == -1
    assert state.job.state == "printing"


def test_a_new_job_number_replaces_a_job_without_one() -> None:
    state = apply(PrinterState(), info_with(project=project_with(task_id="-1")))
    replaced = apply(state, info_with(project={"task_id": 7, "progress": 1}))
    assert replaced.job is not None
    assert replaced.job.task_id == 7
    assert replaced.job.progress == 1  # merged: -1 names no job
    # Two real numbers that differ are two jobs.
    other = apply(replaced, info_with(project={"task_id": 8}))
    assert other.job is not None
    assert other.job.progress is None


# -- D10: filament-change steps ------------------------------------------------


@pytest.mark.parametrize(
    ("state", "data", "expected"),
    [
        (
            "extfilbox_filament_feeding",
            {"channel_no": 2, "taskid": "-1"},
            FilamentFeed(FeedSource.PRINTER_FEEDER, 1),
        ),
        (
            "ace_filament_feeding",
            {"channel_no": 1, "taskid": 5, "unit_no": 1},
            FilamentFeed(FeedSource.ACE, 0, unit_no=1),
        ),
        (
            "ace_filament_feeding",
            {"channel_no": "2", "taskid": 5, "unit_no": "x"},
            FilamentFeed(FeedSource.ACE, 1),
        ),
        ("extfilbox_filament_unfeeding", {"channel_no": 1, "taskid": 5}, None),
        ("nozzle_purging", {"channel_no": 1, "taskid": 5}, None),
        ("extfilbox_filament_feeding", {"channel_no": 0}, None),
        ("extfilbox_filament_feeding", {"channel_no": "x"}, None),
        ("printing", {"channel_no": 2}, None),
    ],
)
def test_filament_feed_from_a_step(
    state: str, data: dict[str, Any], expected: FilamentFeed | None
) -> None:
    assert filament_feed("start", state, data) == expected
    report = parse_message(step(state, **data))
    assert isinstance(report, PrintReport)
    assert report.feed == expected
    assert report.job_state is None or state == "printing"


def test_untagged_channel_is_a_channel_feed() -> None:
    assert filament_feed("update", "updated", {"channel_no": 4}) == FilamentFeed(
        FeedSource.CHANNEL, 3
    )
    assert filament_feed("query", "updated", {"channel_no": 4}) is None
    assert filament_feed("update", "updated", None) is None
    refused = message(
        "print", {"channel_no": 4}, action="update", state="updated", code=10500
    )
    report = parse_message(refused)
    assert isinstance(report, PrintReport)
    assert report.feed is None


def test_steps_never_touch_the_job(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    running = project_with(task_id=5)
    state = apply(PrinterState(), info_with(state="busy", project=running))
    sequence = [
        step("extfilbox_filament_feeding", channel_no=1, taskid=5),
        step("nozzle_purging", channel_no=1, taskid=5),
        step("extfilbox_filament_unfeeding", channel_no=1, taskid=5),
        step("extfilbox_filament_feeding", channel_no=2, taskid=5),
        step("ace_filament_feeding", channel_no=1, taskid=5, unit_no=1),
        step("nozzle_purging", channel_no=1, taskid=5),
        step("ace_filament_feeding", channel_no=2, taskid=5, unit_no=1),
    ]
    channels = []
    for payload in sequence:
        state = apply(state, payload)
        channels.append(state.channel_no)
        assert state.job is not None
        assert state.job.state == "printing"
        assert state.job.task_id == 5
    # Purge and unfeed leave the last feeding channel as it was.
    assert channels == [1, 1, 1, 2, 1, 1, 2]
    assert not [r for r in caplog.records if r.levelno > logging.DEBUG]


def test_steps_numbered_minus_one_create_no_job() -> None:
    state = apply(
        PrinterState(),
        info_with(state="busy"),
        step("ace_filament_feeding", channel_no=1, taskid="-1", unit_no=1),
        step("nozzle_purging", channel_no=1, taskid="-1"),
    )
    assert state.job is None
    assert state.channel_no == 1


# -- D13: current_filament ------------------------------------------------------


def extfilbox_auto(value: object) -> dict[str, Any]:
    return message(
        "extfilbox", {"current_filament": value}, action="auto", state="done", code=200
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0-3", FilamentFeed(FeedSource.CURRENT_FILAMENT, 3, box=0)),
        ("1-0", FilamentFeed(FeedSource.CURRENT_FILAMENT, 0, box=1)),
        (" 0-2 ", FilamentFeed(FeedSource.CURRENT_FILAMENT, 2, box=0)),
        ("", None),
        ("0-", None),
        ("-1-2", None),
        ("a-b", None),
        ("3", None),
        (3, None),
        (None, None),
    ],
)
def test_current_filament(value: object, expected: FilamentFeed | None) -> None:
    assert current_filament(value) == expected
    report = parse_message(extfilbox_auto(value))
    assert isinstance(report, ExternalFilamentBoxReport)
    assert report.feed == expected
    assert not report.is_holder_report


def test_current_filament_leaves_the_holder() -> None:
    holder = message(
        "extfilbox",
        {"id": 1, "type": "PLA", "color": [1, 2, 3], "loaded": 1},
        action="reportInfo",
        state="success",
    )
    state = apply(PrinterState(), holder, extfilbox_auto("0-3"))
    assert state.external_filament_box is not None
    assert state.external_filament_box["type"] == "PLA"
    report = parse_message(holder)
    assert isinstance(report, ExternalFilamentBoxReport)
    assert report.feed is None
    assert report.is_holder_report


def test_current_filament_only_from_a_completed_auto_report() -> None:
    report = parse_message(extfilbox_auto("0-3") | {"state": "failed"})
    assert isinstance(report, ExternalFilamentBoxReport)
    assert report.feed is None


# -- D11: ACE 2 Pro drying report without a temperature -------------------------

DRYING = {
    "duration": 14400,
    "humidity": 28,
    "remain_time": 162,
    "status": 1,
    "target_temp": 50,
}


@pytest.mark.parametrize(
    "data",
    [
        {"multi_color_box": [{"id": 0, "drying_status": DRYING}]},
        {"multi_color_box": {"id": 0, "drying_status": DRYING}},
        {"id": 0, "drying_status": DRYING},
    ],
)
def test_drying_report_without_temperature(
    data: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    full = message(
        "multiColorBox",
        {"multi_color_box": [ACE_BOX | {"temp": 31}]},
        action="getInfo",
        state="success",
    )
    report = message(
        "multiColorBox", data, action="autoUpdateDryStatus", state="success"
    )
    state = apply(PrinterState(), full, report)
    box = state.ace_boxes[0]
    assert box.temp == 31
    assert box.drying is not None
    assert box.drying.status == 1
    assert box.drying.target_temp == 50
    assert box.drying.duration == 14400
    assert box.drying.remain_time == 162
    assert box.drying.humidity == 28
    assert box.slots == state.ace_boxes[0].slots
    assert len(box.slots) == 1
    assert not [r for r in caplog.records if r.levelno > logging.DEBUG]


def test_a_box_object_without_an_id_is_not_a_box() -> None:
    report = parse_message(
        message(
            "multiColorBox", {"drying_status": DRYING}, action="autoUpdateDryStatus"
        )
    )
    assert report is not None
    assert getattr(report, "boxes", ()) is None


# -- D14: logs name no printer --------------------------------------------------


def test_unparsable_payload_log_hides_the_topic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    topic = "anycubic/anycubicCloud/v1/printer/public/20025/SECRETDEVICE/info/report"
    assert parse_message(b"not json", topic) is None
    assert "SECRETDEVICE" not in caplog.text
    assert "info" in caplog.text
