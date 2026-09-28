"""Merging successive reports into one PrinterState."""

from __future__ import annotations

from typing import Any

import pytest

from anycubic_lan.models import PrinterStatus, PrintStatus, SpeedMode
from anycubic_lan.reports import Position, PrinterState, parse_message

from .payloads import (
    ACE_BOX,
    AI_SETTINGS_REPORT,
    AXIS_COORDINATES,
    FAN,
    INFO_IDLE,
    PERIPHERIE_REPORT,
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


@pytest.mark.parametrize(
    ("job_state", "status"),
    [
        ("downloading", PrinterStatus.PRINTING),
        ("preheating", PrinterStatus.PRINTING),
        ("pausing", PrinterStatus.PAUSED),
        ("paused", PrinterStatus.PAUSED),
        ("resuming", PrinterStatus.PRINTING),
        ("resumed", PrinterStatus.PRINTING),
        ("stopping", PrinterStatus.BUSY),
        ("stopped", PrinterStatus.IDLE),
        ("stoped", PrinterStatus.IDLE),
        ("failed", PrinterStatus.IDLE),
        ("canceled", PrinterStatus.IDLE),
        ("cancelled", PrinterStatus.IDLE),
    ],
)
def test_status_from_job_state_words(job_state: str, status: PrinterStatus) -> None:
    # Q3 in docs/QUESTIONS.md. print_status 0 is "keep", so only the state
    # word decides; info.state is "free" so an over job falls back to idle.
    project = project_with(state=job_state, print_status=0, pause=0)
    state = apply(PrinterState(), info_with(state="free", project=project))
    assert state.status is status


def test_stopped_job_is_not_printing() -> None:
    stopped = project_with(state="stoped", print_status=1)
    state = apply(PrinterState(), info_with(state="busy", project=stopped))
    assert state.status is PrinterStatus.BUSY


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


def ace(action: str, state: str, *boxes: Any, **envelope: Any) -> dict[str, Any]:
    """A multiColorBox report in the shape of Q1 in docs/QUESTIONS.md."""
    return message(
        "multiColorBox",
        {"multi_color_box": list(boxes)},
        action=action,
        state=state,
        **envelope,
    )


SECOND_BOX: dict[str, Any] = {**ACE_BOX, "id": 1, "temp": 30}


def test_ace_boxes_replace() -> None:
    state = apply(PrinterState(), ace("getInfo", "success", ACE_BOX, SECOND_BOX))
    assert [b.id for b in state.ace_boxes] == [0, 1]
    assert state.ace_boxes[0].loaded_slot == 0
    state = apply(state, message("multiColorBox", None))
    assert len(state.ace_boxes) == 2  # nothing found: kept
    state = apply(state, ace("getInfo", "done", ACE_BOX))
    assert [b.id for b in state.ace_boxes] == [0]  # a full list replaces


def test_ace_bare_list_tolerated() -> None:
    state = apply(
        PrinterState(),
        {
            "type": "multiColorBox",
            "action": "getInfo",
            "state": "success",
            "data": [ACE_BOX],
        },
    )
    assert len(state.ace_boxes) == 1


def test_ace_auto_update_info_changes_loaded_slot_only() -> None:
    state = apply(
        PrinterState(),
        ace("getInfo", "success", ACE_BOX, SECOND_BOX),
        ace("autoUpdateInfo", "done", {"id": 1, "loaded_slot": 0}),
    )
    first, second = state.ace_boxes
    assert second.loaded_slot_raw == 0
    assert second.temp == 30
    assert len(second.slots) == 1
    assert second.drying is not None
    assert first.loaded_slot_raw == -1


def test_ace_dry_status_updates_temp_and_drying() -> None:
    drying = {"status": 1, "target_temp": 55, "duration": 240, "remain_time": 200}
    for action in ("autoUpdateDryStatus", "setDry"):
        state = apply(
            PrinterState(),
            ace("getInfo", "success", ACE_BOX),
            ace(action, "success", {"id": 0, "temp": 41, "drying_status": drying}),
            ace(action, "success", {"id": 0, "drying_status": {"remain_time": 190}}),
        )
        (box,) = state.ace_boxes
        assert box.temp == 41
        assert box.drying is not None
        assert box.drying.is_drying
        assert box.drying.target_temp == 55
        assert box.drying.remain_time == 190
        assert box.slots[0].material == "PLA"


def test_ace_drying_reported_for_box_without_drying() -> None:
    state = apply(
        PrinterState(),
        ace("getInfo", "success", {"id": 0, "temp": 25}),
        ace("setDry", "success", {"id": 0, "drying_status": {"status": 1}}),
    )
    assert state.ace_boxes[0].drying is not None
    assert state.ace_boxes[0].drying.is_drying


def test_ace_set_info_and_refresh_update_slots() -> None:
    new_slot = {"index": 0, "type": "PETG", "color": [0, 0, 0], "edit_status": 1}
    extra_slot = {"index": 1, "type": "ABS", "status": 4}
    for action in ("setInfo", "refresh"):
        state = apply(
            PrinterState(),
            ace("getInfo", "success", ACE_BOX),
            ace(action, "success", {"id": 0, "slots": [new_slot, extra_slot]}),
        )
        (box,) = state.ace_boxes
        assert [s.material for s in box.slots] == ["PETG", "ABS"]
        assert box.slots[0].color == (0, 0, 0)
        assert box.slots[0].status == 5  # not reported: kept
        assert box.temp == 25


def test_ace_feed_filament() -> None:
    state = apply(
        PrinterState(),
        ace("getInfo", "success", ACE_BOX),
        ace("feedFilament", "done", {"id": 0, "loaded_slot": 0, "feed_status": 1}),
    )
    (box,) = state.ace_boxes
    assert box.loaded_slot == 0
    assert box.feed_status == 1


def test_ace_partial_before_full_list_and_without_id() -> None:
    state = apply(
        PrinterState(),
        ace("autoUpdateInfo", "done", {"id": 1, "loaded_slot": 2}),
        ace("autoUpdateInfo", "done", {"loaded_slot": 3}),  # no id: dropped
    )
    (box,) = state.ace_boxes
    assert (box.id, box.loaded_slot) == (1, 2)


def test_ace_failed_report_changes_nothing() -> None:
    state = apply(
        PrinterState(),
        ace("getInfo", "success", ACE_BOX),
        ace("setDry", "failed", {"id": 0, "temp": 99}, code=10801),
    )
    assert state.ace_boxes[0].temp == 25
    assert state.last_error_code == 10801


def test_ai_settings_and_peripherals_merge() -> None:
    state = apply(
        PrinterState(),
        AI_SETTINGS_REPORT,
        message("aiSettings", {"ai_settings": {"count": 30}}),
        message("peripherie", {"camera": 1}),
        message("peripherie", {"multiColorBox": 1}),
    )
    assert state.ai_settings is not None
    assert state.ai_settings.count == 30
    assert state.ai_settings.status == 0
    assert state.ai_settings.notice_type == (0, 1)
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


def print_report(action: str, state: str, **fields: Any) -> dict[str, Any]:
    """A print report in the shape of Q2 in docs/QUESTIONS.md: the project
    block with the task id under ``taskid``."""
    data = {k: v for k, v in PROJECT.items() if k != "task_id"}
    data["taskid"] = str(PROJECT["task_id"])
    data.update(fields)
    return message("print", data, action=action, state=state, code=200)


@pytest.mark.parametrize(
    ("action", "job_state", "status"),
    [
        ("start", "downloading", PrinterStatus.PRINTING),
        ("start", "checking", PrinterStatus.PRINTING),
        ("start", "preheating", PrinterStatus.PRINTING),
        ("start", "printing", PrinterStatus.PRINTING),
        ("pause", "pausing", PrinterStatus.PAUSED),
        ("pause", "paused", PrinterStatus.PAUSED),
        ("resume", "resuming", PrinterStatus.PRINTING),
        ("resume", "resumed", PrinterStatus.PRINTING),
        ("stop", "stopping", PrinterStatus.BUSY),
    ],
)
def test_print_report_updates_job(
    action: str, job_state: str, status: PrinterStatus
) -> None:
    state = apply(
        PrinterState(),
        info_with(state="busy", project=PROJECT),
        print_report(action, job_state, progress=65),
    )
    assert state.job is not None
    assert state.job.task_id == 614707220
    assert state.job.state == job_state
    assert state.job.progress == 65
    assert state.job.total_layers == 5
    assert state.status is status


@pytest.mark.parametrize(
    ("action", "job_state"),
    [("start", "finished"), ("stop", "stopped"), ("stop", "stoped")],
)
def test_print_report_ends_job(action: str, job_state: str) -> None:
    state = apply(
        PrinterState(),
        info_with(state="free", project=PROJECT),
        print_report(action, job_state),
    )
    assert state.job is not None
    assert state.job.is_finished
    assert state.status is PrinterStatus.IDLE
    # info.project stays authoritative: null clears the job.
    state = apply(state, INFO_IDLE)
    assert state.job is None


def test_print_report_starts_job_when_none_known() -> None:
    state = apply(PrinterState(), INFO_IDLE, print_report("start", "preheating"))
    assert state.job is not None
    assert state.job.task_id == 614707220
    assert state.status is PrinterStatus.PRINTING


def test_print_report_does_not_revive_an_over_job() -> None:
    state = apply(PrinterState(), INFO_IDLE, print_report("stop", "stoped"))
    assert state.job is None
    assert state.status is PrinterStatus.IDLE


def test_info_project_overrides_print_report() -> None:
    state = apply(
        PrinterState(),
        info_with(state="busy", project=PROJECT),
        print_report("pause", "paused"),
        info_with(state="busy", project=project_with(state="printing")),
    )
    assert state.status is PrinterStatus.PRINTING


def test_print_report_integer_taskid_and_data_state() -> None:
    state = apply(
        PrinterState(),
        info_with(project=PROJECT),
        message("print", {"taskid": 614707220, "state": "paused"}),
    )
    assert state.job is not None
    assert state.job.state == "paused"  # "done" is not a job state
    assert state.job.progress == 60


def test_print_report_without_task_changes_nothing() -> None:
    state = apply(
        PrinterState(),
        info_with(project=PROJECT),
        message("print", {"progress": 99}, action="pause", state="paused"),
        message("print", None, action="pause", state="paused"),
        message("print", {"taskid": "abc"}, action="pause", state="paused"),
    )
    assert state.job is not None
    assert state.job.progress == 60
    assert state.job.state == "printing"


def test_print_report_other_task_replaces_job() -> None:
    state = apply(
        PrinterState(),
        info_with(project=PROJECT),
        message("print", {"taskid": "9", "progress": 1}, state="printing"),
    )
    assert state.job is not None
    assert state.job.task_id == 9
    assert state.job.total_layers is None


@pytest.mark.parametrize("action", ["pause", "resume", "stop"])
def test_failed_command_is_an_error_not_a_job_state(action: str) -> None:
    # Q2 in docs/QUESTIONS.md: state failed with a non-OK code.
    state = apply(
        PrinterState(),
        info_with(state="busy", project=PROJECT),
        print_report(action, "failed") | {"code": 10500, "msg": "refused"},
    )
    assert state.last_error_code == 10500
    assert state.last_error_message == "refused"
    assert state.job is not None
    assert state.job.state == "printing"  # "failed" is not applied to the job
    assert state.status is PrinterStatus.PRINTING
    # The next OK print report clears the error.
    state = apply(state, print_report(action, "paused"))
    assert state.last_error is None


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


def test_live_ai_settings_and_peripherie() -> None:
    state = apply(PrinterState(), AI_SETTINGS_REPORT, PERIPHERIE_REPORT)
    assert state.ai_settings is not None
    assert state.ai_settings.sensitivity_level == (1, 1)
    assert state.peripherals is not None
    assert state.has_camera is True
    assert state.peripherals.ace is True
    assert state.peripherals.usb_disk is True
