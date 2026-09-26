"""Enumerations and lookup tables from PROTOCOL.md."""

from __future__ import annotations

from enum import IntEnum, StrEnum

#: Topic prefix shared by every report and command (PROTOCOL.md §4).
TOPIC_PREFIX = "anycubic/anycubicCloud/v1"

#: Printer model ids (PROTOCOL.md §9).
PRINTER_MODELS: dict[int, str] = {
    20025: "Kobra S1",
    20030: "Kobra X",
}

#: Filament hub model ids (PROTOCOL.md §6.7).
ACE_MODELS: dict[int, str] = {
    40002: "ACE Pro",
}

#: The light a Kobra S1 lets a client control (PROTOCOL.md §6.5).
DEFAULT_LIGHT_TYPE = 2

#: Slot ``status`` meaning "this slot feeds the printer" (PROTOCOL.md §6.7).
SLOT_STATUS_LOADED = 5

#: Envelope ``state`` words meaning "completed". ``success`` and ``done`` are
#: equivalent for every report kind (Q1 in docs/QUESTIONS.md).
COMPLETED_STATES = frozenset({"success", "done"})

#: Envelope ``state`` of a command the printer refused (Q2).
STATE_FAILED = "failed"

#: Job ``state`` words meaning the job is over (Q3 in docs/QUESTIONS.md).
#: ``stoped`` is the firmware's own spelling; both ``canceled`` and
#: ``cancelled`` occur.
JOB_OVER_STATES = frozenset(
    {"finished", "stopped", "stoped", "failed", "canceled", "cancelled"}
)

#: Job ``state`` words meaning the job is paused or pausing (Q3).
JOB_PAUSED_STATES = frozenset({"pausing", "paused"})

#: Job ``state`` words meaning the job is leaving a pause (Q3). They win over
#: a ``pause`` flag that has not caught up yet.
JOB_RESUMING_STATES = frozenset({"resuming", "resumed"})

#: Job ``state`` words meaning a stop is under way but not finished (Q3).
JOB_STOPPING_STATES = frozenset({"stopping"})


def printer_model_name(model_id: int) -> str:
    """Return the model name for ``model_id``.

    Unknown ids are reported as ``"Anycubic printer (model <id>)"``
    (PROTOCOL.md §9).
    """
    return PRINTER_MODELS.get(model_id, f"Anycubic printer (model {model_id})")


class PrintStatus(IntEnum):
    """``project.print_status`` (PROTOCOL.md §6.2).

    ``0``, ``8``, any other number and non-numbers are not statuses: a job
    that reports one keeps its previous status. :meth:`from_raw` returns
    ``None`` for them.
    """

    PRINTING = 1
    COMPLETE = 2
    CANCELLED = 3
    DOWNLOADING = 4
    CHECKING = 5
    PREHEATING = 6
    SLICING = 7
    LEVELLING = 9

    @classmethod
    def from_raw(cls, value: object) -> PrintStatus | None:
        """Map a raw value; ``None`` means "keep the previous status"."""
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        try:
            return cls(value)
        except ValueError:
            return None


class SpeedMode(IntEnum):
    """``print_speed_mode`` presets observed on the Kobra S1 (PROTOCOL.md §6.1)."""

    SILENT = 1
    STANDARD = 2
    SPORT = 3

    @classmethod
    def from_raw(cls, value: object) -> SpeedMode | None:
        """Map a raw value; ``None`` for unknown values (keep the raw one)."""
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        try:
            return cls(value)
        except ValueError:
            return None


class PrinterStatus(StrEnum):
    """Overall printer status derived from ``info.state`` and the current job.

    A job that is ``pausing`` or ``paused`` reads as :attr:`PAUSED`;
    ``resuming`` and ``resumed`` read as :attr:`PRINTING`; ``stopping`` reads
    as :attr:`BUSY` until the job is over (Q3 in docs/QUESTIONS.md).
    """

    IDLE = "idle"
    PRINTING = "printing"
    PAUSED = "paused"
    BUSY = "busy"
    UNKNOWN = "unknown"


class ReportKind(StrEnum):
    """Report kinds, spelled as the printer spells them (PROTOCOL.md §6)."""

    INFO = "info"
    TEMPERATURE = "tempature"  # sic: the firmware's spelling
    FAN = "fan"
    LIGHT = "light"
    MULTI_COLOR_BOX = "multiColorBox"
    PRINT = "print"
    AI_SETTINGS = "aiSettings"
    PERIPHERALS = "peripherie"  # sic
    AXIS = "axis"
    EXTERNAL_FILAMENT_BOX = "extfilbox"


#: ``multiColorBox`` action whose answer is the full box list (Q1). Other
#: actions (``setInfo``, ``refresh``, ``autoUpdateInfo``,
#: ``autoUpdateDryStatus``, ``setDry``, ``feedFilament``) carry only the boxes
#: and fields they changed.
ACE_FULL_LIST_ACTION = "getInfo"

#: Query action per kind (PROTOCOL.md §7.1). ``multiColorBox`` only answers
#: ``getInfo``.
QUERY_ACTIONS: dict[ReportKind, str] = {
    ReportKind.INFO: "query",
    ReportKind.TEMPERATURE: "query",
    ReportKind.FAN: "query",
    ReportKind.LIGHT: "query",
    ReportKind.MULTI_COLOR_BOX: "getInfo",
    ReportKind.PRINT: "query",
    ReportKind.AI_SETTINGS: "query",
    ReportKind.PERIPHERALS: "query",
    ReportKind.AXIS: "query",
    ReportKind.EXTERNAL_FILAMENT_BOX: "query",
}
