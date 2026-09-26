"""Pure parser for printer reports (PROTOCOL.md §5 and §6).

Nothing in this module does I/O. :func:`parse_message` turns one MQTT payload
into a typed, frozen report object (or ``None`` for messages that must be
ignored), and :meth:`PrinterState.apply` folds successive reports into one
merged state.

Every field is parsed on its own: a value of an unexpected type becomes
``None`` and the rest of the report is kept (PROTOCOL.md §5).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, cast

from .models import (
    DEFAULT_LIGHT_TYPE,
    SLOT_STATUS_LOADED,
    PrinterStatus,
    PrintStatus,
    ReportKind,
    SpeedMode,
)

_LOGGER = logging.getLogger(__name__)

type Number = int | float

_EMPTY_FEATURES: Mapping[str, bool] = MappingProxyType({})
_EMPTY_ERRORS: Mapping[str, ReportCode] = MappingProxyType({})
_KNOWN_KINDS = frozenset(kind.value for kind in ReportKind)

#: ``code`` values meaning "processed / nothing wrong" (PROTOCOL.md §5;
#: QUESTIONS.md Q4: both 0 and 200 occur).
OK_CODES = frozenset({0, 200})

#: Job ``state`` words that mean the job is over (QUESTIONS.md Q3).
_JOB_OVER_STATES = frozenset(
    {"finished", "stopped", "stoped", "failed", "canceled", "cancelled"}
)
_JOB_PAUSED_STATES = frozenset({"pausing", "paused"})


# --------------------------------------------------------------------------
# Field helpers: each returns None for anything it does not recognise and
# never raises.
# --------------------------------------------------------------------------


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _num(value: object) -> Number | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _map(value: object) -> Mapping[str, Any] | None:
    return cast("Mapping[str, Any]", value) if isinstance(value, Mapping) else None


def _int_tuple(value: object) -> tuple[int, ...] | None:
    if not isinstance(value, list):
        return None
    return tuple(i for i in (_int(v) for v in value) if i is not None)


def _code(value: object) -> int | None:
    # QUESTIONS.md Q4: a non-integer or boolean ``code`` is treated as absent.
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _task_id(data: Mapping[str, Any]) -> int | None:
    # ``info.project`` says ``task_id``; the ``print`` report says ``taskid``
    # (QUESTIONS.md Q2). Commands send it as a string, so accept digits too.
    for key in ("task_id", "taskid"):
        value = data.get(key)
        if (parsed := _int(value)) is not None:
            return parsed
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _merge[T](old: T, new: T) -> T:
    """Return ``old`` with every non-``None`` field of ``new`` applied."""
    changes = {
        f.name: getattr(new, f.name)
        for f in fields(cast("Any", new))
        if getattr(new, f.name) is not None
    }
    return cast("T", replace(cast("Any", old), **changes))


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Envelope:
    """The fields every report carries (PROTOCOL.md §5)."""

    kind: str
    action: str | None = None
    state: str | None = None
    code: int | None = None
    msg: str | None = None
    msgid: str | None = None
    timestamp: int | None = None
    topic: str | None = None
    data: object = field(default=None, repr=False, compare=False)

    @property
    def is_error(self) -> bool:
        """``True`` when the printer reported a code other than 0 or 200."""
        return self.code is not None and self.code not in OK_CODES

    @property
    def is_completed(self) -> bool:
        """``state`` is ``done`` or ``success`` (equivalent; QUESTIONS.md Q1)."""
        return self.state in ("done", "success")


@dataclass(frozen=True, slots=True)
class Temperatures:
    """Temperatures in °C; ``None`` when not reported (PROTOCOL.md §6.1, §6.3)."""

    nozzle: Number | None = None
    nozzle_target: Number | None = None
    bed: Number | None = None
    bed_target: Number | None = None
    chamber: Number | None = None
    chamber_target: Number | None = None

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> Temperatures:
        return cls(
            nozzle=_num(data.get("curr_nozzle_temp")),
            nozzle_target=_num(data.get("target_nozzle_temp")),
            bed=_num(data.get("curr_hotbed_temp")),
            bed_target=_num(data.get("target_hotbed_temp")),
            chamber=_num(data.get("curr_chamber_temp")),
            chamber_target=_num(data.get("target_chamber_temp")),
        )


@dataclass(frozen=True, slots=True)
class Fans:
    """Fan readings; missing is not zero (PROTOCOL.md §6.4)."""

    fan_speed_pct: Number | None = None
    aux_fan_speed_pct: Number | None = None
    box_fan_level: int | None = None

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> Fans:
        return cls(
            fan_speed_pct=_num(data.get("fan_speed_pct")),
            aux_fan_speed_pct=_num(data.get("aux_fan_speed_pct")),
            box_fan_level=_int(data.get("box_fan_level")),
        )


@dataclass(frozen=True, slots=True)
class Job:
    """The current (or last) print job (PROTOCOL.md §6.2)."""

    task_id: int | None = None
    filename: str | None = None
    progress: Number | None = None
    current_layer: int | None = None
    total_layers: int | None = None
    print_time: Number | None = None
    """Minutes elapsed."""
    remain_time: Number | None = None
    """Minutes remaining."""
    supplies_usage: Number | None = None
    pause: bool | None = None
    state: str | None = None
    print_status: PrintStatus | None = None
    """``None`` when the printer sent 0 or an unknown value."""
    print_status_raw: int | None = None
    speed_mode_raw: int | None = None
    project_type: int | None = None
    local_task: str | None = None

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> Job:
        raw_status = data.get("print_status")
        return cls(
            task_id=_task_id(data),
            filename=_str(data.get("filename")),
            progress=_num(data.get("progress")),
            current_layer=_int(data.get("curr_layer")),
            total_layers=_int(data.get("total_layers")),
            print_time=_num(data.get("print_time")),
            remain_time=_num(data.get("remain_time")),
            supplies_usage=_num(data.get("supplies_usage")),
            pause=_bool(data.get("pause")),
            state=_str(data.get("state")),
            print_status=PrintStatus.from_raw(raw_status),
            print_status_raw=_int(raw_status),
            speed_mode_raw=_int(data.get("print_speed_mode")),
            project_type=_int(data.get("project_type")),
            local_task=_str(data.get("localtask")),
        )

    @property
    def name(self) -> str | None:
        """File name without directories and extension."""
        if not self.filename:
            return None
        return PurePosixPath(self.filename.replace("\\", "/")).stem or None

    @property
    def is_paused(self) -> bool:
        return bool(self.pause) or self.state in _JOB_PAUSED_STATES

    @property
    def is_finished(self) -> bool:
        """The job is over: ``print_status`` 2 or 3, or a terminal ``state``."""
        return (
            self.print_status in (PrintStatus.COMPLETE, PrintStatus.CANCELLED)
            or self.state in _JOB_OVER_STATES
        )


@dataclass(frozen=True, slots=True)
class Light:
    """One light (PROTOCOL.md §6.5)."""

    type: int | None = None
    on: bool | None = None
    brightness: int | None = None

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> Light:
        return cls(
            type=_int(data.get("type")),
            on=_bool(data.get("status")),
            brightness=_int(data.get("brightness")),
        )


@dataclass(frozen=True, slots=True)
class Position:
    """Head position in mm (PROTOCOL.md §6.6)."""

    x: Number | None = None
    y: Number | None = None
    z: Number | None = None


@dataclass(frozen=True, slots=True)
class AceDrying:
    """``drying_status`` of an ACE box (PROTOCOL.md §6.7)."""

    status: int | None = None
    target_temp: Number | None = None
    duration: Number | None = None
    """Minutes."""
    remain_time: Number | None = None
    """Minutes."""

    @property
    def is_drying(self) -> bool:
        return bool(self.status)


@dataclass(frozen=True, slots=True)
class AceSlot:
    """One filament slot of an ACE box (PROTOCOL.md §6.7)."""

    index: int | None = None
    material: str | None = None
    color: tuple[int, int, int] | None = None
    sku: str | None = None
    status: int | None = None
    edit_status: int | None = None
    """0 = read from RFID, 1 = entered by hand, 2 = slot empty."""

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> AceSlot:
        color = None
        raw_color = data.get("color")
        if isinstance(raw_color, list) and len(raw_color) == 3:
            parts = [_int(c) for c in raw_color]
            if all(p is not None for p in parts):
                red, green, blue = cast("list[int]", parts)
                color = (red, green, blue)
        return cls(
            index=_int(data.get("index")),
            material=_str(data.get("type")),
            color=color,
            sku=_str(data.get("sku")),
            status=_int(data.get("status")),
            edit_status=_int(data.get("edit_status")),
        )

    @property
    def is_loaded(self) -> bool:
        return self.status == SLOT_STATUS_LOADED


@dataclass(frozen=True, slots=True)
class AceBox:
    """One ACE filament hub (PROTOCOL.md §6.7)."""

    id: int | None = None
    status: int | None = None
    model_id: int | None = None
    auto_feed: bool | None = None
    loaded_slot_raw: int | None = None
    temp: Number | None = None
    drying: AceDrying | None = None
    slots: tuple[AceSlot, ...] | None = None
    """``None`` when the report did not carry slots."""

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> AceBox:
        drying = None
        if (raw_drying := _map(data.get("drying_status"))) is not None:
            drying = AceDrying(
                status=_int(raw_drying.get("status")),
                target_temp=_num(raw_drying.get("target_temp")),
                duration=_num(raw_drying.get("duration")),
                remain_time=_num(raw_drying.get("remain_time")),
            )
        slots: tuple[AceSlot, ...] | None = None
        if isinstance(raw_slots := data.get("slots"), list):
            slots = tuple(
                AceSlot.from_data(slot)
                for s in raw_slots
                if (slot := _map(s)) is not None
            )
        return cls(
            id=_int(data.get("id")),
            status=_int(data.get("status")),
            model_id=_int(data.get("model_id")),
            auto_feed=_bool(data.get("auto_feed")),
            loaded_slot_raw=_int(data.get("loaded_slot")),
            temp=_num(data.get("temp")),
            drying=drying,
            slots=slots,
        )

    @property
    def loaded_slot(self) -> int | None:
        """Index of the slot feeding the printer, or ``None``.

        ``loaded_slot`` of ``-1`` means "none reported"; the slot whose own
        status is 5 is then the loaded one. Best-effort (PROTOCOL.md §6.7).
        """
        if self.loaded_slot_raw is not None and self.loaded_slot_raw >= 0:
            return self.loaded_slot_raw
        for slot in self.slots or ():
            if slot.is_loaded:
                return slot.index
        return None


@dataclass(frozen=True, slots=True)
class AiSettings:
    """AI failure detection settings (PROTOCOL.md §6.8)."""

    status: int | None = None
    type: int | None = None
    count: int | None = None
    notice_type: tuple[int, ...] | None = None
    sensitivity_level: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class Peripherals:
    """Which peripherals are fitted (PROTOCOL.md §6.9)."""

    camera: bool | None = None
    ace: bool | None = None
    usb_disk: bool | None = None


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Report:
    """Base class of every parsed report."""

    envelope: Envelope

    @property
    def kind(self) -> str:
        return self.envelope.kind


@dataclass(frozen=True, slots=True)
class InfoReport(Report):
    """The main state report (PROTOCOL.md §6.1)."""

    printer_name: str | None = None
    model: str | None = None
    ip: str | None = None
    firmware_version: str | None = None
    printer_state: str | None = None
    camera_url: str | None = None
    file_upload_url: str | None = field(default=None, repr=False)
    temperatures: Temperatures | None = None
    fans: Fans = Fans()
    speed_mode_raw: int | None = None
    features: Mapping[str, bool] | None = None
    project: Job | None = None
    project_reported: bool = False
    """``True`` when ``project`` was present (possibly ``null``) in the report."""
    last_project: Job | None = None
    last_project_reported: bool = False


@dataclass(frozen=True, slots=True)
class TemperatureReport(Report):
    """``tempature`` report (PROTOCOL.md §6.3)."""

    temperatures: Temperatures = Temperatures()


@dataclass(frozen=True, slots=True)
class FanReport(Report):
    """``fan`` report (PROTOCOL.md §6.4)."""

    fans: Fans = Fans()


@dataclass(frozen=True, slots=True)
class LightReport(Report):
    """``light`` report (PROTOCOL.md §6.5)."""

    lights: tuple[Light, ...] = ()
    full_list: bool = False
    """``True`` for a query answer (the whole list), ``False`` for one light."""


@dataclass(frozen=True, slots=True)
class AxisReport(Report):
    """``axis`` report (PROTOCOL.md §6.6); ``position`` may be ``None``."""

    position: Position | None = None


@dataclass(frozen=True, slots=True)
class MultiColorBoxReport(Report):
    """``multiColorBox`` report (PROTOCOL.md §6.7).

    ``boxes`` is ``None`` when no box list could be found in the payload.
    """

    boxes: tuple[AceBox, ...] | None = None


@dataclass(frozen=True, slots=True)
class AiSettingsReport(Report):
    """``aiSettings`` report (PROTOCOL.md §6.8)."""

    settings: AiSettings = AiSettings()


@dataclass(frozen=True, slots=True)
class PeripheralsReport(Report):
    """``peripherie`` report (PROTOCOL.md §6.9)."""

    peripherals: Peripherals = Peripherals()


@dataclass(frozen=True, slots=True)
class ExternalFilamentBoxReport(Report):
    """``extfilbox`` report; its shape is undocumented, so only raw data."""

    data: Mapping[str, Any] | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class PrintReport(Report):
    """``print`` report (PROTOCOL.md §6.9), also the answer to job commands."""

    job: Job | None = None


@dataclass(frozen=True, slots=True)
class UnknownReport(Report):
    """A report of a kind this library does not parse."""


# --------------------------------------------------------------------------
# Message parsing
# --------------------------------------------------------------------------


def kind_from_topic(topic: str | None) -> str | None:
    """Return the last topic segment that names a report kind, if any."""
    if not topic:
        return None
    for segment in reversed(topic.split("/")):
        if segment in _KNOWN_KINDS:
            return segment
    return None


def _decode(payload: bytes | str | Mapping[str, Any]) -> Mapping[str, Any] | None:
    if isinstance(payload, Mapping):
        return payload
    try:
        decoded = json.loads(payload)
    except (ValueError, TypeError):
        return None
    return _map(decoded)


def parse_message(
    payload: bytes | str | Mapping[str, Any], topic: str | None = None
) -> Report | None:
    """Parse one MQTT payload.

    Returns ``None`` for messages that carry nothing: non-JSON or non-object
    payloads, messages whose ``type`` is empty, bare acknowledgements
    (``{"msgid": ""}``) and single-key messages on a ``response`` topic.
    """
    message = _decode(payload)
    if message is None:
        _LOGGER.debug("Ignoring non-JSON-object payload on %s", topic)
        return None

    raw_type = message.get("type")
    if raw_type == "":
        return None  # Kobra X emits many of these; they carry nothing.
    if topic is not None and "response" in topic.split("/") and len(message) <= 1:
        return None
    if "type" not in message and set(message) <= {"msgid"}:
        return None  # bare acknowledgement
    kind = _str(raw_type) or kind_from_topic(topic)
    if not kind:
        return None

    envelope = Envelope(
        kind=kind,
        action=_str(message.get("action")),
        state=_str(message.get("state")),
        code=_code(message.get("code")),
        msg=_str(message.get("msg")),
        msgid=_str(message.get("msgid")),
        timestamp=_int(message.get("timestamp")),
        topic=topic,
        data=message.get("data"),
    )
    parser = _PARSERS.get(kind)
    if parser is None:
        return UnknownReport(envelope)
    return parser(envelope, _map(message.get("data")))


def _parse_info(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    if data is None:
        return InfoReport(envelope)
    urls = _map(data.get("urls")) or {}
    temp = _map(data.get("temp"))
    features = None
    if (raw_features := _map(data.get("features"))) is not None:
        features = MappingProxyType(
            {k: v for k, v in raw_features.items() if isinstance(v, bool)}
        )
    project = _map(data.get("project"))
    last_project = _map(data.get("last_project"))
    return InfoReport(
        envelope,
        printer_name=_str(data.get("printerName")),
        model=_str(data.get("model")),
        ip=_str(data.get("ip")),
        firmware_version=_str(data.get("version")),
        printer_state=_str(data.get("state")),
        camera_url=_str(urls.get("rtspUrl")),
        file_upload_url=_str(urls.get("fileUploadurl")),
        temperatures=Temperatures.from_data(temp) if temp is not None else None,
        fans=Fans.from_data(data),
        speed_mode_raw=_int(data.get("print_speed_mode")),
        features=features,
        project=Job.from_data(project) if project is not None else None,
        # A project that is present but not an object (null, or garbage) is
        # treated as "no job": that is the only documented non-object value.
        project_reported="project" in data,
        last_project=Job.from_data(last_project) if last_project is not None else None,
        last_project_reported="last_project" in data,
    )


def _parse_temperature(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    return TemperatureReport(envelope, temperatures=Temperatures.from_data(data or {}))


def _parse_fan(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    return FanReport(envelope, fans=Fans.from_data(data or {}))


def _parse_light(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    if data is None:
        return LightReport(envelope)
    if isinstance(raw := data.get("lights"), list):
        lights = tuple(
            Light.from_data(light) for item in raw if (light := _map(item)) is not None
        )
        return LightReport(envelope, lights=lights, full_list=True)
    return LightReport(envelope, lights=(Light.from_data(data),))


def _parse_axis(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    coordinates = _map((data or {}).get("coordinates"))
    if coordinates is None:
        return AxisReport(envelope)
    return AxisReport(
        envelope,
        position=Position(
            x=_num(coordinates.get("x")),
            y=_num(coordinates.get("y")),
            z=_num(coordinates.get("z")),
        ),
    )


def _parse_multi_color_box(
    envelope: Envelope, data: Mapping[str, Any] | None
) -> Report:
    # The boxes are the list under ``data.multi_color_box`` (QUESTIONS.md Q1).
    raw = (data or {}).get("multi_color_box")
    if not isinstance(raw, list):
        return MultiColorBoxReport(envelope)
    boxes = tuple(AceBox.from_data(box) for b in raw if (box := _map(b)) is not None)
    return MultiColorBoxReport(envelope, boxes=boxes)


def _parse_ai_settings(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    data = data or {}
    return AiSettingsReport(
        envelope,
        settings=AiSettings(
            status=_int(data.get("status")),
            type=_int(data.get("type")),
            count=_int(data.get("count")),
            notice_type=_int_tuple(data.get("notice_type")),
            sensitivity_level=_int_tuple(data.get("sensitivity_level")),
        ),
    )


def _parse_peripherals(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    data = data or {}
    return PeripheralsReport(
        envelope,
        peripherals=Peripherals(
            camera=_bool(data.get("camera")),
            ace=_bool(data.get("ace")),
            usb_disk=_bool(data.get("usb_disk")),
        ),
    )


def _parse_extfilbox(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    return ExternalFilamentBoxReport(envelope, data=data)


def _parse_print(envelope: Envelope, data: Mapping[str, Any] | None) -> Report:
    # QUESTIONS.md Q2: ``data`` carries the job fields. ``info.project`` stays
    # the authoritative job (``print`` is silent when idle), so a ``print``
    # report does not change the merged state's job.
    return PrintReport(envelope, job=Job.from_data(data) if data else None)


_PARSERS = {
    ReportKind.INFO.value: _parse_info,
    ReportKind.TEMPERATURE.value: _parse_temperature,
    ReportKind.FAN.value: _parse_fan,
    ReportKind.LIGHT.value: _parse_light,
    ReportKind.AXIS.value: _parse_axis,
    ReportKind.MULTI_COLOR_BOX.value: _parse_multi_color_box,
    ReportKind.AI_SETTINGS.value: _parse_ai_settings,
    ReportKind.PERIPHERALS.value: _parse_peripherals,
    ReportKind.EXTERNAL_FILAMENT_BOX.value: _parse_extfilbox,
    ReportKind.PRINT.value: _parse_print,
}


# --------------------------------------------------------------------------
# Merged state
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReportCode:
    """A non-200 ``code`` the printer reported for one report kind."""

    kind: str
    code: int
    message: str | None = None


@dataclass(frozen=True, slots=True)
class PrinterState:
    """Everything known about one printer, merged from successive reports.

    Instances are immutable; :meth:`apply` returns a new instance. A field
    missing from a report keeps its previous value.
    """

    printer_name: str | None = None
    model: str | None = None
    ip: str | None = None
    firmware_version: str | None = None
    printer_state: str | None = None
    """Raw ``info.state``: ``free``, ``busy`` or another word."""
    camera_url: str | None = None
    """HTTP-FLV stream URL (``info.urls.rtspUrl``)."""
    file_upload_url: str | None = field(default=None, repr=False)
    temperatures: Temperatures = Temperatures()
    has_chamber: bool = False
    """``True`` once a non-zero chamber temperature has been seen."""
    fans: Fans = Fans()
    speed_mode_raw: int | None = None
    features: Mapping[str, bool] = _EMPTY_FEATURES
    job: Job | None = None
    last_job: Job | None = None
    lights: tuple[Light, ...] = ()
    position: Position | None = None
    ace_boxes: tuple[AceBox, ...] = ()
    ai_settings: AiSettings | None = None
    peripherals: Peripherals | None = None
    external_filament_box: Mapping[str, Any] | None = field(default=None, repr=False)
    errors: Mapping[str, ReportCode] = _EMPTY_ERRORS
    """Open non-200 codes per report kind, oldest first."""

    # -- derived values ---------------------------------------------------

    @property
    def status(self) -> PrinterStatus:
        """Overall status: idle, printing, paused, busy or unknown."""
        job = self.job
        if job is not None and not job.is_finished:
            return PrinterStatus.PAUSED if job.is_paused else PrinterStatus.PRINTING
        if self.printer_state == "free":
            return PrinterStatus.IDLE
        if self.printer_state == "busy":
            return PrinterStatus.BUSY
        return PrinterStatus.UNKNOWN

    @property
    def speed_mode(self) -> SpeedMode | None:
        return SpeedMode.from_raw(self.speed_mode_raw)

    @property
    def job_status(self) -> PrintStatus | None:
        """Status of the current job; ``None`` when there is no job."""
        return self.job.print_status if self.job is not None else None

    @property
    def last_error(self) -> ReportCode | None:
        """The most recent non-200 code that has not been cleared since."""
        # QUESTIONS.md Q4: the printer sends no explicit "cleared" message; the
        # next OK code (0 or 200) for the same report kind clears it.
        if not self.errors:
            return None
        return list(self.errors.values())[-1]

    @property
    def last_error_code(self) -> int | None:
        error = self.last_error
        return error.code if error is not None else None

    @property
    def last_error_message(self) -> str | None:
        error = self.last_error
        return error.message if error is not None else None

    @property
    def light(self) -> Light | None:
        """The controllable light (type 2), else the first one reported."""
        for light in self.lights:
            if light.type == DEFAULT_LIGHT_TYPE:
                return light
        return self.lights[0] if self.lights else None

    @property
    def has_camera(self) -> bool | None:
        return self.peripherals.camera if self.peripherals is not None else None

    # -- merging ------------------------------------------------------------

    def apply(self, report: Report) -> PrinterState:
        """Return a new state with ``report`` merged in."""
        state = self._apply_code(report.envelope)
        match report:
            case InfoReport():
                return state._apply_info(report)
            case TemperatureReport():
                return state._apply_temperatures(report.temperatures)
            case FanReport():
                return replace(state, fans=_merge(state.fans, report.fans))
            case LightReport():
                return state._apply_lights(report)
            case AxisReport(position=Position() as position):
                return replace(state, position=position)
            case MultiColorBoxReport(boxes=tuple() as boxes):
                if report.envelope.action == "getInfo":
                    return replace(state, ace_boxes=boxes)
                return replace(state, ace_boxes=_merge_boxes(state.ace_boxes, boxes))
            case AiSettingsReport():
                return replace(
                    state,
                    ai_settings=_merge(state.ai_settings, report.settings)
                    if state.ai_settings is not None
                    else report.settings,
                )
            case PeripheralsReport():
                return replace(
                    state,
                    peripherals=_merge(state.peripherals, report.peripherals)
                    if state.peripherals is not None
                    else report.peripherals,
                )
            case ExternalFilamentBoxReport(data=Mapping() as data):
                return replace(state, external_filament_box=data)
        return state

    def _apply_code(self, envelope: Envelope) -> PrinterState:
        if envelope.code is None:
            return self
        errors = dict(self.errors)
        errors.pop(envelope.kind, None)
        if envelope.code not in OK_CODES:
            errors[envelope.kind] = ReportCode(
                envelope.kind, envelope.code, envelope.msg
            )
        elif len(errors) == len(self.errors):
            return self
        return replace(self, errors=MappingProxyType(errors))

    def _apply_temperatures(self, temperatures: Temperatures) -> PrinterState:
        chamber = temperatures.chamber
        return replace(
            self,
            temperatures=_merge(self.temperatures, temperatures),
            has_chamber=self.has_chamber or bool(chamber),
        )

    def _apply_info(self, report: InfoReport) -> PrinterState:
        state = self
        if report.temperatures is not None:
            state = state._apply_temperatures(report.temperatures)
        changes: dict[str, Any] = {
            name: value
            for name in (
                "printer_name",
                "model",
                "ip",
                "firmware_version",
                "printer_state",
                "camera_url",
                "file_upload_url",
                "speed_mode_raw",
                "features",
            )
            if (value := getattr(report, name)) is not None
        }
        changes["fans"] = _merge(state.fans, report.fans)
        if report.project_reported:
            changes["job"] = _merge_job(state.job, report.project)
        if report.last_project_reported:
            changes["last_job"] = report.last_project
        return replace(state, **changes)

    def _apply_lights(self, report: LightReport) -> PrinterState:
        if report.full_list:
            return replace(self, lights=report.lights)
        lights = list(self.lights)
        for light in report.lights:
            for i, known in enumerate(lights):
                if known.type == light.type:
                    lights[i] = _merge(known, light)
                    break
            else:
                lights.append(light)
        return replace(self, lights=tuple(lights))


def _merge_job(previous: Job | None, new: Job | None) -> Job | None:
    """Merge a reported project block into the known job.

    ``None`` (``project: null``) clears the job. The same job (same task id,
    or an unknown id on either side) is merged field by field, so a
    ``print_status`` of 0 keeps the previous status. A different task id is a
    new job and replaces the old one.
    """
    if new is None or previous is None:
        return new
    if (
        new.task_id is not None
        and previous.task_id is not None
        and new.task_id != previous.task_id
    ):
        return new
    return _merge(previous, new)


def _merge_boxes(
    known: tuple[AceBox, ...], reported: tuple[AceBox, ...]
) -> tuple[AceBox, ...]:
    """Merge a partial box list (every action but ``getInfo``) by box id.

    ``autoUpdateInfo``, ``setDry``, ``feedFilament`` and others carry only
    some fields of some boxes (QUESTIONS.md Q1); the rest is kept.
    """
    boxes = list(known)
    for box in reported:
        for i, old in enumerate(boxes):
            if box.id is not None and old.id == box.id:
                boxes[i] = _merge(old, box)
                break
        else:
            boxes.append(box)
    return tuple(boxes)
