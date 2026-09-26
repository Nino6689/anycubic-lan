"""Parser tests: one report at a time (PROTOCOL.md §5, §6)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from anycubic_lan.models import PrintStatus, SpeedMode
from anycubic_lan.reports import (
    AceBox,
    AceSlot,
    AiSettingsReport,
    AxisReport,
    ExternalFilamentBoxReport,
    FanReport,
    InfoReport,
    Job,
    LightReport,
    MultiColorBoxReport,
    PeripheralsReport,
    Position,
    PrintReport,
    TemperatureReport,
    UnknownReport,
    kind_from_topic,
    parse_message,
)

from .payloads import (
    ACE_BOX,
    AI_SETTINGS,
    AXIS_COORDINATES,
    ENVELOPE,
    FAN,
    INFO_IDLE,
    PROJECT,
    TEMPATURE,
    info_with,
    message,
    project_with,
)

REPORT_TOPIC = "anycubic/anycubicCloud/v1/printer/public/20025/DEVICE1234/info/report"


def _parse(payload: Any, topic: str | None = None) -> Any:
    report = parse_message(payload, topic)
    assert report is not None
    return report


# -- envelope -----------------------------------------------------------------


def test_envelope_fields() -> None:
    report = _parse(json.dumps(ENVELOPE).encode(), REPORT_TOPIC)
    assert isinstance(report, InfoReport)
    env = report.envelope
    assert report.kind == "info"
    assert env.action == "report"
    assert env.timestamp == 244516
    assert env.msgid == "b85ca099-9792-4e2d-83df-cdd6f1a7296d"
    assert env.state == "done"
    assert env.code == 200
    assert env.msg == "done"
    assert env.topic == REPORT_TOPIC
    assert not env.is_error


def test_envelope_accepts_str_payload() -> None:
    report = _parse(json.dumps({**ENVELOPE, "code": 10801}))
    assert report.envelope.code == 10801
    assert report.envelope.is_error


@pytest.mark.parametrize("code", [0, 200])
def test_envelope_ok_codes(code: int) -> None:
    # Q4 in docs/QUESTIONS.md: 0 and 200 both mean OK.
    report = _parse({**ENVELOPE, "code": code})
    assert report.envelope.code == code
    assert not report.envelope.is_error


@pytest.mark.parametrize("code", ["10801", "200", 200.0, 1.5, True, False, None, [1]])
def test_envelope_non_integer_code_is_absent(code: Any) -> None:
    # Q4 in docs/QUESTIONS.md: a non-integer or boolean code is absent.
    report = _parse({**ENVELOPE, "code": code})
    assert report.envelope.code is None
    assert not report.envelope.is_error


def test_envelope_bad_values_become_none() -> None:
    report = _parse({**ENVELOPE, "code": "x", "timestamp": "late", "msg": 5})
    assert report.envelope.code is None
    assert report.envelope.timestamp is None
    assert report.envelope.msg is None


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[1, 2]",
        b"\xff\xfe",
        {"msgid": ""},  # bare acknowledgement
        {},
        {"type": "", "action": "report", "data": {"x": 1}},  # empty type
    ],
)
def test_ignored_messages(payload: Any) -> None:
    assert parse_message(payload, REPORT_TOPIC) is None


def test_single_key_on_response_topic_ignored() -> None:
    topic = "anycubic/anycubicCloud/v1/printer/public/20025/DEVICE1234/response"
    assert parse_message({"action": "x"}, topic) is None


def test_type_absent_uses_topic() -> None:
    report = _parse({"action": "query", "data": FAN["data"]}, "a/b/fan/report")
    assert isinstance(report, FanReport)
    assert report.fans.fan_speed_pct == 55


def test_type_absent_and_no_kind_in_topic_ignored() -> None:
    assert parse_message({"action": "query", "data": {}}, "a/b/c") is None
    assert parse_message({"action": "query", "data": {}}) is None


def test_non_string_type_falls_back_to_topic() -> None:
    report = _parse({"type": 7, "data": FAN["data"]}, "x/fan/report")
    assert isinstance(report, FanReport)


def test_kind_from_topic_picks_last_known_segment() -> None:
    assert kind_from_topic("p/info/light/report") == "light"
    assert kind_from_topic("p/multiColorBox/report/extra") == "multiColorBox"
    assert kind_from_topic("p/nothing/here") is None
    assert kind_from_topic("") is None
    assert kind_from_topic(None) is None


def test_unknown_kind() -> None:
    report = _parse({"type": "somethingNew", "data": {"a": 1}, "code": 200})
    assert isinstance(report, UnknownReport)
    assert report.envelope.data == {"a": 1}


# -- info ---------------------------------------------------------------------


def test_info_idle() -> None:
    report = _parse(INFO_IDLE)
    assert isinstance(report, InfoReport)
    assert report.printer_name == "Anycubic Kobra S1"
    assert report.model == "Anycubic Kobra S1"
    assert report.ip == "10.0.66.28"
    assert report.firmware_version == "2.7.2.7"
    assert report.printer_state == "free"
    assert report.camera_url == "http://10.0.66.28:18088/flv"
    assert report.file_upload_url == "http://10.0.66.28:18910/gcode_upload?s=SIGNED"
    assert report.temperatures is not None
    assert report.temperatures.bed == 31
    assert report.temperatures.nozzle == 34
    assert report.temperatures.bed_target == 0
    assert report.temperatures.nozzle_target == 0
    assert report.temperatures.chamber is None
    assert report.speed_mode_raw == 2
    assert report.fans.fan_speed_pct == 0
    assert report.fans.aux_fan_speed_pct == 0
    assert report.fans.box_fan_level == 0
    assert report.project is None
    assert report.project_reported
    assert report.last_project is None
    assert report.last_project_reported
    assert report.features is not None
    assert report.features["auto_leveling_support"] is True
    assert len(report.features) == 12


def test_info_with_project() -> None:
    report = _parse(info_with(state="busy", project=PROJECT))
    job = report.project
    assert isinstance(job, Job)
    assert job.task_id == 614707220
    assert job.progress == 60
    assert job.current_layer == 3
    assert job.total_layers == 5
    assert job.print_time == 7
    assert job.remain_time == 42
    assert job.supplies_usage == 120
    assert job.pause is False
    assert job.state == "printing"
    assert job.print_status is PrintStatus.PRINTING
    assert job.print_status_raw == 1
    assert job.speed_mode_raw is None
    assert job.project_type == 1
    assert job.local_task == "b92a60d8-44d0-4b2a-916f-e5f476a07143"
    assert job.name == "0622-1002-Spectacular Wolt (1)_plate(01)_PLA_0.2_45s"
    assert not job.is_paused
    assert not job.is_finished


def test_info_last_project_nested_object_tolerated() -> None:
    last = project_with(state="finished", print_status=2, progress=100)
    report = _parse(info_with(last_project=last))
    assert report.project is None
    assert report.last_project is not None
    assert report.last_project.print_status is PrintStatus.COMPLETE
    assert report.last_project.is_finished


def test_info_one_bad_field_keeps_the_rest() -> None:
    report = _parse(
        info_with(
            version=["not", "a", "string"],
            temp={"curr_nozzle_temp": "hot", "curr_hotbed_temp": 60},
            urls="garbage",
            features={"a": True, "b": "yes"},
            print_speed_mode="fast",
            fan_speed_pct=True,
        )
    )
    assert report.firmware_version is None
    assert report.printer_name == "Anycubic Kobra S1"
    assert report.temperatures.nozzle is None
    assert report.temperatures.bed == 60
    assert report.camera_url is None
    assert dict(report.features) == {"a": True}
    assert report.speed_mode_raw is None
    assert report.fans.fan_speed_pct is None


def test_info_absent_fields() -> None:
    report = _parse({"type": "info", "data": {"state": "busy"}})
    assert report.temperatures is None
    assert report.features is None
    assert not report.project_reported
    assert not report.last_project_reported


def test_info_without_data() -> None:
    report = _parse({"type": "info", "data": None})
    assert isinstance(report, InfoReport)
    assert report.printer_state is None


def test_project_non_object_is_no_job() -> None:
    report = _parse(info_with(project="weird"))
    assert report.project is None
    assert report.project_reported


@pytest.mark.parametrize("raw", [0, 8, 42, "1", None, True, 1.5])
def test_print_status_not_a_status(raw: Any) -> None:
    job = Job.from_data(project_with(print_status=raw))
    assert job.print_status is None
    assert job.task_id == 614707220  # the rest of the block still applies


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1, PrintStatus.PRINTING),
        (2, PrintStatus.COMPLETE),
        (3, PrintStatus.CANCELLED),
        (4, PrintStatus.DOWNLOADING),
        (5, PrintStatus.CHECKING),
        (6, PrintStatus.PREHEATING),
        (7, PrintStatus.SLICING),
        (9, PrintStatus.LEVELLING),
    ],
)
def test_print_status_values(raw: int, expected: PrintStatus) -> None:
    assert Job.from_data(project_with(print_status=raw)).print_status is expected


def test_job_float_values_and_paused() -> None:
    job = Job.from_data(project_with(curr_layer=4.0, progress=61.5, pause=1))
    assert job.current_layer == 4
    assert job.progress == 61.5
    assert job.is_paused
    assert Job.from_data(project_with(state="paused")).is_paused
    assert Job.from_data(project_with(progress=float("nan"))).progress is None


@pytest.mark.parametrize(
    "state",
    ["finished", "stopped", "stoped", "failed", "canceled", "cancelled"],
)
def test_job_over_states(state: str) -> None:
    # Q3 in docs/QUESTIONS.md: the job-over state words.
    job = Job.from_data(project_with(state=state, print_status=0))
    assert job.is_finished


@pytest.mark.parametrize(
    "state",
    [
        "downloading",
        "checking",
        "preheating",
        "auto_leveling",
        "printing",
        "pausing",
        "paused",
        "resuming",
        "resumed",
        "stopping",
    ],
)
def test_job_not_over_states(state: str) -> None:
    job = Job.from_data(project_with(state=state, print_status=0))
    assert not job.is_finished


@pytest.mark.parametrize("print_status", [2, 3])
def test_job_over_by_print_status(print_status: int) -> None:
    job = Job.from_data(project_with(state="printing", print_status=print_status))
    assert job.is_finished


def test_job_pause_states() -> None:
    assert Job.from_data(project_with(state="pausing")).is_paused
    assert Job.from_data(project_with(state="paused")).is_paused
    # resuming/resumed win over a pause flag that has not caught up yet.
    assert not Job.from_data(project_with(state="resuming", pause=1)).is_paused
    assert not Job.from_data(project_with(state="resumed", pause=1)).is_paused
    assert Job.from_data(project_with(state="stopping")).is_stopping
    assert not Job.from_data(PROJECT).is_stopping


@pytest.mark.parametrize(
    ("filename", "name"),
    [
        ("plain.gcode", "plain"),
        ("a/b/c.d.gcode", "c.d"),
        ("C:\\files\\win.gcode", "win"),
        ("", None),
        (None, None),
    ],
)
def test_job_name(filename: str | None, name: str | None) -> None:
    assert Job(filename=filename).name == name


# -- tempature ----------------------------------------------------------------


def test_tempature() -> None:
    report = _parse(TEMPATURE)
    assert isinstance(report, TemperatureReport)
    t = report.temperatures
    assert (t.bed, t.nozzle, t.chamber) == (31, 34, 0)
    assert (t.bed_target, t.nozzle_target, t.chamber_target) == (0, 0, 0)


def test_tempature_without_data() -> None:
    report = _parse({"type": "tempature", "data": None})
    assert report.temperatures.nozzle is None


# -- fan ----------------------------------------------------------------------


def test_fan() -> None:
    report = _parse(FAN)
    assert isinstance(report, FanReport)
    assert report.fans.fan_speed_pct == 55
    assert report.fans.aux_fan_speed_pct == 0
    assert report.fans.box_fan_level == 0


def test_fan_missing_is_not_zero() -> None:
    report = _parse(message("fan", {"fan_speed_pct": 20}))
    assert report.fans.fan_speed_pct == 20
    assert report.fans.aux_fan_speed_pct is None
    assert report.fans.box_fan_level is None


# -- light --------------------------------------------------------------------


def test_light_query_answer_is_a_list() -> None:
    report = _parse(
        message(
            "light",
            {
                "lights": [
                    {"type": 2, "status": 1, "brightness": 80},
                    {"type": 1, "status": 0, "brightness": 0},
                    "junk",
                ]
            },
        )
    )
    assert isinstance(report, LightReport)
    assert report.full_list
    assert [(x.type, x.on, x.brightness) for x in report.lights] == [
        (2, True, 80),
        (1, False, 0),
    ]


def test_light_control_answer_is_single() -> None:
    report = _parse(
        message("light", {"type": 2, "status": 0, "brightness": 100}, action="control")
    )
    assert not report.full_list
    assert len(report.lights) == 1
    assert report.lights[0].on is False
    assert report.lights[0].brightness == 100


def test_light_without_data() -> None:
    report = _parse(message("light", None))
    assert report.lights == ()


def test_light_bad_status() -> None:
    report = _parse(message("light", {"type": 2, "status": 7, "brightness": "x"}))
    assert report.lights[0].on is None
    assert report.lights[0].brightness is None


# -- axis ---------------------------------------------------------------------


def test_axis_with_coordinates() -> None:
    report = _parse(message("axis", {"coordinates": AXIS_COORDINATES}))
    assert isinstance(report, AxisReport)
    assert report.position == Position(x=47, y=276, z=3.8152532726237904)


def test_axis_without_coordinates() -> None:
    assert _parse(message("axis", {})).position is None


def test_axis_move_done_null_data() -> None:
    report = _parse(message("axis", None, action="move"))
    assert report.envelope.action == "move"
    assert report.position is None


# -- multiColorBox ------------------------------------------------------------


def test_multi_color_box() -> None:
    report = _parse(
        message(
            "multiColorBox",
            {"multi_color_box": [ACE_BOX]},
            action="getInfo",
            state="success",
        )
    )
    assert isinstance(report, MultiColorBoxReport)
    assert report.is_full_list
    assert report.envelope.is_completed
    assert report.boxes is not None
    (box,) = report.boxes
    assert isinstance(box, AceBox)
    assert box.id == 0
    assert box.status == 1
    assert box.model_id == 40002
    assert box.auto_feed is False
    assert box.temp == 25
    assert box.loaded_slot_raw == -1
    assert box.drying is not None
    assert not box.drying.is_drying
    (slot,) = box.slots
    assert isinstance(slot, AceSlot)
    assert slot.index == 0
    assert slot.material == "PLA"
    assert slot.color == (255, 255, 255)
    assert slot.sku == ""
    assert slot.status == 5
    assert slot.edit_status == 0
    assert slot.is_loaded
    assert box.feed_status is None


@pytest.mark.parametrize("state", ["success", "done"])
def test_get_info_success_and_done_are_both_full(state: str) -> None:
    # Q1 in docs/QUESTIONS.md: success and done are equivalent.
    report = _parse(
        message(
            "multiColorBox",
            {"multi_color_box": [ACE_BOX]},
            action="getInfo",
            state=state,
        )
    )
    assert report.is_full_list


@pytest.mark.parametrize(
    ("action", "state"),
    [
        ("getInfo", "failed"),
        ("setInfo", "success"),
        ("refresh", "success"),
        ("autoUpdateInfo", "done"),
        ("autoUpdateDryStatus", "success"),
        ("setDry", "success"),
        ("feedFilament", "done"),
    ],
)
def test_other_ace_actions_are_partial(action: str, state: str) -> None:
    report = _parse(
        message(
            "multiColorBox",
            {"multi_color_box": [{"id": 0, "loaded_slot": 1}]},
            action=action,
            state=state,
        )
    )
    assert report.boxes is not None
    assert not report.is_full_list


@pytest.mark.parametrize("raw", [3, "feeding", None, True, 1.5])
def test_feed_status(raw: Any) -> None:
    box = AceBox.from_data({"id": 0, "loaded_slot": 1, "feed_status": raw})
    expected = (
        raw if isinstance(raw, (str, int)) and not isinstance(raw, bool) else None
    )
    assert box.feed_status == expected


def test_loaded_slot_minus_one_falls_back_to_status_5() -> None:
    box = AceBox.from_data(ACE_BOX)
    assert box.loaded_slot == 0


def test_loaded_slot_reported() -> None:
    slots = [
        {"index": 0, "status": 5},
        {"index": 1, "status": 4},
    ]
    assert (
        AceBox.from_data({**ACE_BOX, "loaded_slot": 1, "slots": slots}).loaded_slot == 1
    )


def test_loaded_slot_none() -> None:
    slots = [{"index": 0, "status": 1}]
    assert AceBox.from_data({**ACE_BOX, "slots": slots}).loaded_slot is None
    assert AceBox.from_data({"loaded_slot": "?"}).loaded_slot is None


def test_ace_drying_and_bad_fields() -> None:
    box = AceBox.from_data(
        {
            **ACE_BOX,
            "drying_status": {
                "status": 1,
                "target_temp": 55,
                "duration": 240,
                "remain_time": 200,
            },
            "slots": [{"index": 1, "color": [1, "x", 3]}, {"color": [1, 2]}, 3],
        }
    )
    assert box.drying is not None
    assert box.drying.is_drying
    assert box.drying.target_temp == 55
    assert box.drying.remain_time == 200
    assert [s.color for s in box.slots] == [None, None]
    assert box.slots[0].index == 1


def test_multi_color_box_data_is_list() -> None:
    report = _parse({"type": "multiColorBox", "data": [ACE_BOX, ACE_BOX]})
    assert report.boxes is not None
    assert len(report.boxes) == 2


def test_multi_color_box_without_boxes() -> None:
    assert _parse(message("multiColorBox", {"x": 1})).boxes is None
    assert _parse(message("multiColorBox", None)).boxes is None
    # Only data.multi_color_box holds the list (Q1), not any other list.
    assert _parse(message("multiColorBox", {"boxes": [ACE_BOX]})).boxes is None
    assert _parse(message("multiColorBox", {"multi_color_box": {}})).boxes is None
    empty = _parse(message("multiColorBox", {"multi_color_box": []}))
    assert empty.boxes == ()


# -- aiSettings, peripherie, extfilbox, print ---------------------------------


def test_ai_settings() -> None:
    report = _parse(message("aiSettings", AI_SETTINGS))
    assert isinstance(report, AiSettingsReport)
    s = report.settings
    assert (s.status, s.type, s.count) == (3, 2, 60)
    assert s.notice_type == (0, 1)
    assert s.sensitivity_level == (1, 1)


def test_ai_settings_bad_lists() -> None:
    report = _parse(
        message("aiSettings", {"notice_type": "x", "sensitivity_level": [1, "a"]})
    )
    assert report.settings.notice_type is None
    assert report.settings.sensitivity_level == (1,)


def test_peripherie() -> None:
    report = _parse(
        message("peripherie", {"camera": True, "ace": True, "usb_disk": False})
    )
    assert isinstance(report, PeripheralsReport)
    p = report.peripherals
    assert (p.camera, p.ace, p.usb_disk) == (True, True, False)


def test_peripherie_without_data() -> None:
    assert _parse(message("peripherie", None)).peripherals.camera is None


def test_extfilbox() -> None:
    report = _parse(message("extfilbox", {"anything": 1}))
    assert isinstance(report, ExternalFilamentBoxReport)
    assert report.data == {"anything": 1}


def test_print_report() -> None:
    report = _parse(message("print", PROJECT))
    assert isinstance(report, PrintReport)
    assert report.job is not None
    assert report.job.task_id == 614707220


def test_print_report_command_answer() -> None:
    report = _parse(message("print", None, action="pause", code=200, msgid="abc"))
    assert report.job is None
    assert report.envelope.msgid == "abc"


def test_speed_mode_enum() -> None:
    assert SpeedMode.from_raw(1) is SpeedMode.SILENT
    assert SpeedMode.from_raw(3) is SpeedMode.SPORT
    assert SpeedMode.from_raw(9) is None
    assert SpeedMode.from_raw(True) is None
