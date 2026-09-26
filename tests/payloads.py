"""Payloads copied from docs/PROTOCOL.md (the only source used by the tests)."""

from __future__ import annotations

import copy
from typing import Any

# PROTOCOL.md §2
DISCOVERY: dict[str, Any] = {
    "ctrlType": "lan",
    "token": "0123456789abcdeffedcba9876543210",
    "ctrlInfoUrl": "http://10.0.66.28:18910/ctrl",
    "modelId": 20025,
    "cn": "SERIAL123",
    "usn": "uuid:fdm:A4-E8-8D-80-54-C8",
    "modelName": "Anycubic Kobra S1",
    "deviceType": "fdm",
}

# PROTOCOL.md §3.5
CREDENTIALS: dict[str, Any] = {
    "broker": "mqtts://10.0.66.28:9883",
    "username": "printer-user",
    "password": "printer-pass",
    "deviceId": "DEVICE1234",
}

# PROTOCOL.md §5
ENVELOPE: dict[str, Any] = {
    "type": "info",
    "action": "report",
    "timestamp": 244516,
    "msgid": "b85ca099-9792-4e2d-83df-cdd6f1a7296d",
    "state": "done",
    "code": 200,
    "msg": "done",
    "data": {},
}

# PROTOCOL.md §6.1 (Kobra S1 idle)
INFO_IDLE: dict[str, Any] = {
    "type": "info",
    "action": "report",
    "state": "done",
    "code": 200,
    "msg": "done",
    "data": {
        "printerName": "Anycubic Kobra S1",
        "model": "Anycubic Kobra S1",
        "ip": "10.0.66.28",
        "version": "2.7.2.7",
        "state": "free",
        "urls": {
            "fileUploadurl": "http://10.0.66.28:18910/gcode_upload?s=SIGNED",
            "rtspUrl": "http://10.0.66.28:18088/flv",
        },
        "temp": {
            "curr_hotbed_temp": 31,
            "curr_nozzle_temp": 34,
            "target_hotbed_temp": 0,
            "target_nozzle_temp": 0,
        },
        "print_speed_mode": 2,
        "fan_speed_pct": 0,
        "aux_fan_speed_pct": 0,
        "box_fan_level": 0,
        "project": None,
        "last_project": None,
        "features": {
            "auto_leveling_support": True,
            "vibration_compensation_support": True,
            "flow_calibration_support": True,
            "drying_first_support": True,
            "camera_timelapse_support": True,
            "gcode_3mf_support": True,
            "delete_batch_support": True,
            "preheating_support": True,
            "fod_support": True,
            "shengwang_rtc_support": True,
            "pre_cancel_support": True,
            "shengwang_rdt_support": True,
        },
    },
}

# PROTOCOL.md §6.2 (Kobra S1 mid-print)
PROJECT: dict[str, Any] = {
    "remain_time": 42,
    "curr_layer": 3,
    "total_layers": 5,
    "supplies_usage": 120,
    "print_time": 7,
    "progress": 60,
    "state": "printing",
    "print_status": 1,
    "filename": ".3mf_temp/0622-1002-Spectacular Wolt (1)_plate(01)_PLA_0.2_45s.gcode",
    "pause": 0,
    "project_type": 1,
    "task_id": 614707220,
    "localtask": "b92a60d8-44d0-4b2a-916f-e5f476a07143",
    "task_settings": {"camera_timelapse": 0},
    "print_speed_mode": None,
}

# PROTOCOL.md §6.3
TEMPATURE: dict[str, Any] = {
    "type": "tempature",
    "action": "query",
    "state": "done",
    "data": {
        "curr_hotbed_temp": 31,
        "curr_nozzle_temp": 34,
        "curr_chamber_temp": 0,
        "target_hotbed_temp": 0,
        "target_nozzle_temp": 0,
        "target_chamber_temp": 0,
    },
}

# PROTOCOL.md §6.4
FAN: dict[str, Any] = {
    "type": "fan",
    "action": "query",
    "state": "done",
    "data": {"aux_fan_speed_pct": 0, "box_fan_level": 0, "fan_speed_pct": 55},
}

# PROTOCOL.md §6.6
AXIS_COORDINATES: dict[str, Any] = {"x": 47, "y": 276, "z": 3.8152532726237904}

# PROTOCOL.md §6.7
ACE_BOX: dict[str, Any] = {
    "id": 0,
    "status": 1,
    "model_id": 40002,
    "auto_feed": 0,
    "loaded_slot": -1,
    "temp": 25,
    "drying_status": {"status": 0, "target_temp": 0, "duration": 0, "remain_time": 0},
    "slots": [
        {
            "index": 0,
            "sku": "",
            "type": "PLA",
            "color": [255, 255, 255],
            "status": 5,
            "edit_status": 0,
        }
    ],
}

# PROTOCOL.md §6.8
AI_SETTINGS: dict[str, Any] = {
    "status": 3,
    "type": 2,
    "count": 60,
    "notice_type": [0, 1],
    "sensitivity_level": [1, 1],
}


def info_with(**data: Any) -> dict[str, Any]:
    """INFO_IDLE with ``data`` fields replaced."""
    message = copy.deepcopy(INFO_IDLE)
    message["data"].update(data)
    return message


def project_with(**fields: Any) -> dict[str, Any]:
    """PROJECT with fields replaced."""
    project = copy.deepcopy(PROJECT)
    project.update(fields)
    return project


def message(kind: str, data: Any, **envelope: Any) -> dict[str, Any]:
    """A report envelope of ``kind`` around ``data``."""
    return {"type": kind, "action": "query", "state": "done", "data": data, **envelope}
