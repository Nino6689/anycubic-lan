"""Merging successive reports into one PrinterState."""

from __future__ import annotations

from typing import Any

from anycubic_lan.models import PrinterStatus, PrintStatus, SpeedMode
from anycubic_lan.reports import Position, PrinterState, parse_message

from .payloads import (
    ACE_BOX,
    AI_SETTINGS,
    AXIS_COORDINATES,
    FAN,
    INFO_IDLE,
    PROJECT,
    TEMPATURE,
    info_with,
    message,
    project_with,
)


def apply(state: PrinterState, *payloads: Any) -> PrinterState:
    for payload in payloads:
        report = parse_message(payload)
        assert report is not None
        state = state.apply(report)
    return state


def test_empty_state() -> None:
    state = PrinterState()
    assert state.status is PrinterStatus.UNKNOWN
    assert state.job is None
    assert state.job_status is None
    assert state.speed_mode is None
    assert state.light is None
    assert state.has_camera is None
    assert state.last_error is None
    assert state.last_error_code is None
    assert state.last_error_message is None
    assert not state.has_chamber


def test_idle_info() -> None:
    state = apply(PrinterState(), INFO_IDLE)
    assert state.status is PrinterStatus.IDLE
    assert state.firmware_version == "2.7.2.7"
    assert state.camera_url == "http://10.0.66.28:18088/flv"
    assert state.speed_mode is SpeedMode.STANDARD
    assert state.temperatures.nozzle == 34
    assert state.features["fod_support"] is True
    assert state.job is None


def test_busy_without_job_and_unknown_state() -> None:
    assert apply(PrinterState(), info_with(state="busy")).status is PrinterStatus.BUSY
    assert apply(PrinterState(), info_with(state="odd")).status is PrinterStatus.UNKNOWN


def test_printing_and_paused() -> None:
    state = apply(PrinterState(), info_with(state="busy", project=PROJECT))
    assert state.status is PrinterStatus.PRINTING
    assert state.job_status is PrintStatus.PRINTING
    paused = apply(state, info_with(state="busy", project=project_with(pause=1)))
    assert paused.status is PrinterStatus.PAUSED


def test_finished_job_falls_back_to_printer_state() -> None:
    done = project_with(state="finished", print_status=2)
    state = apply(PrinterState(), info_with(state="free", project=done))
    assert state.status is PrinterStatus.IDLE
    assert state.job_status is PrintStatus.COMPLETE


def test_print_status_zero_keeps_prior_status() -> None:
    state = apply(
        PrinterState(),
        info_with(project=project_with(print_status=6)),
        info_with(project=project_with(print_status=0, progress=70)),
    )
    assert state.job is not None
    assert state.job.print_status is PrintStatus.PREHEATING
    assert state.job.progress == 70
    assert state.job.print_status_raw == 0


def test_same_job_missing_fields_keep_previous() -> None:
    partial = {"task_id": 614707220, "progress": 80}
    state = apply(
        PrinterState(), info_with(project=PROJECT), info_with(project=partial)
    )
    assert state.job is not None
    assert state.job.progress == 80
    assert state.job.total_layers == 5
    assert state.job.print_status is PrintStatus.PRINTING


def test_new_task_id_replaces_job() -> None:
    new = {"task_id": 1, "progress": 5, "print_status": 0}
    state = apply(PrinterState(), info_with(project=PROJECT), info_with(project=new))
    assert state.job is not None
    assert state.job.task_id == 1
    assert state.job.total_layers is None
    assert state.job.print_status is None  # the old job's status is not carried over


def test_project_null_clears_job() -> None:
    state = apply(PrinterState(), info_with(project=PROJECT), INFO_IDLE)
    assert state.job is None
    assert state.status is PrinterStatus.IDLE


def test_info_without_project_keeps_job() -> None:
    state = apply(
        PrinterState(),
        info_with(project=PROJECT),
        {"type": "info", "data": {"version": "2.7.2.8"}},
    )
    assert state.job is not None
    assert state.firmware_version == "2.7.2.8"


def test_last_project_recorded() -> None:
    last = project_with(print_status=2)
    state = apply(PrinterState(), info_with(last_project=last))
    assert state.last_job is not None
    assert state.last_job.print_status is PrintStatus.COMPLETE
    state = apply(state, {"type": "info", "data": {"state": "free"}})
    assert state.last_job is not None  # absent: kept


def test_features_kept_when_omitted() -> None:
    state = apply(
        PrinterState(), INFO_IDLE, {"type": "info", "data": {"state": "busy"}}
    )
    assert state.features["gcode_3mf_support"] is True


def test_target_temperatures_from_info_kept_independently() -> None:
    state = apply(
        PrinterState(),
        info_with(temp={"target_nozzle_temp": 210, "target_hotbed_temp": 60}),
        message("tempature", {"curr_nozzle_temp": 200}),
    )
    t = state.temperatures
    assert (t.nozzle, t.nozzle_target, t.bed_target) == (200, 210, 60)
    assert t.bed is None  # the replaced temp block had no current bed value


def test_tempature_merges_and_chamber_flag() -> None:
    state = apply(PrinterState(), TEMPATURE)
    assert state.temperatures.chamber == 0
    assert not state.has_chamber  # always 0 on a chamberless model
    state = apply(state, message("tempature", {"curr_chamber_temp": 35}))
    assert state.has_chamber
    assert state.temperatures.nozzle == 34
    state = apply(state, TEMPATURE)
    assert state.has_chamber


def test_fans_merge() -> None:
    state = apply(PrinterState(), FAN, message("fan", {"aux_fan_speed_pct": 30}))
    assert state.fans.fan_speed_pct == 55
    assert state.fans.aux_fan_speed_pct == 30


def test_lights_merge() -> None:
    state = apply(
        PrinterState(),
        message("light", {"lights": [{"type": 2, "status": 0, "brightness": 50}]}),
        message("light", {"type": 2, "status": 1}, action="control"),
        message("light", {"type": 3, "status": 1, "brightness": 10}, action="control"),
    )
    assert state.light is not None
    assert state.light.on is True
    assert state.light.brightness == 50
    assert len(state.lights) == 2
    state = apply(state, message("light", {"lights": [{"type": 1, "status": 1}]}))
    assert state.light is not None
    assert state.light.type == 1  # no type 2: first light


def test_axis_without_coordinates_keeps_position() -> None:
    state = apply(
        PrinterState(),
        message("axis", {"coordinates": AXIS_COORDINATES}),
        message("axis", {}),
        message("axis", None, action="move"),
    )
    assert state.position == Position(x=47, y=276, z=3.8152532726237904)


def test_ace_boxes_replace() -> None:
    state = apply(PrinterState(), message("multiColorBox", {"boxes": [ACE_BOX]}))
    assert len(state.ace_boxes) == 1
    assert state.ace_boxes[0].loaded_slot == 0
    state = apply(state, message("multiColorBox", None))
    assert len(state.ace_boxes) == 1  # nothing found: kept


def test_ai_settings_and_peripherals_merge() -> None:
    state = apply(
        PrinterState(),
        message("aiSettings", AI_SETTINGS),
        message("aiSettings", {"count": 30}),
        message("peripherie", {"camera": True}),
        message("peripherie", {"ace": True}),
    )
    assert state.ai_settings is not None
    assert state.ai_settings.count == 30
    assert state.ai_settings.status == 3
    assert state.peripherals is not None
    assert state.has_camera is True
    assert state.peripherals.ace is True


def test_extfilbox_and_unknown() -> None:
    state = apply(
        PrinterState(),
        message("extfilbox", {"a": 1}),
        message("extfilbox", None),
        message("newKind", {"b": 2}),
    )
    assert state.external_filament_box == {"a": 1}


def test_print_report_does_not_touch_job() -> None:
    state = apply(
        PrinterState(), info_with(project=PROJECT), message("print", {"task_id": 9})
    )
    assert state.job is not None
    assert state.job.task_id == 614707220


def test_error_codes() -> None:
    state = apply(
        PrinterState(),
        message("multiColorBox", None, code=10801, msg="runout"),
        message("info", {}, code=200),
    )
    assert state.last_error_code == 10801
    assert state.last_error_message == "runout"
    state = apply(state, message("print", None, code=500, msg="nope"))
    assert state.last_error_code == 500
    state = apply(state, message("print", None, code=200))
    assert state.last_error_code == 10801
    state = apply(state, message("multiColorBox", None, code=200))
    assert state.last_error is None


def test_code_zero_clears_like_200() -> None:
    # Q4 in docs/QUESTIONS.md: 0 and 200 both mean OK.
    state = apply(
        PrinterState(), message("multiColorBox", None, code=10801, msg="runout")
    )
    assert state.last_error_code == 10801
    state = apply(state, message("multiColorBox", None, code=0))
    assert state.last_error is None


def test_non_integer_code_neither_raises_nor_clears() -> None:
    state = apply(
        PrinterState(), message("multiColorBox", None, code=10801, msg="runout")
    )
    for code in ("200", True, 200.0):
        state = apply(state, message("multiColorBox", None, code=code))
    assert state.last_error_code == 10801


def test_state_is_immutable_and_apply_returns_new() -> None:
    before = PrinterState()
    after = apply(before, INFO_IDLE)
    assert before.firmware_version is None
    assert after is not before
