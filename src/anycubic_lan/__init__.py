"""Async client for Anycubic 3D printers in LAN Mode.

Typical use::

    async with aiohttp.ClientSession() as session:
        info = await handshake(session, "192.168.1.50")
    client = AnycubicLanClient(info)
    client.add_state_listener(lambda state: print(state.status))
    await client.connect()

See ``docs/PROTOCOL.md`` for the wire protocol this implements.
"""

from __future__ import annotations

from .client import AnycubicLanClient
from .exceptions import (
    AnycubicLanError,
    InvalidResponseError,
    LanModeDisabledError,
    NoActiveJobError,
    NotConnectedError,
    PrinterUnreachableError,
    RequestRejectedError,
    UnsupportedPrinterError,
)
from .handshake import (
    BrokerCredentials,
    DiscoveryInfo,
    PrinterConnectionInfo,
    fetch_discovery,
    handshake,
)
from .models import (
    PrinterStatus,
    PrintStatus,
    ReportKind,
    SpeedMode,
    printer_model_name,
)
from .reports import (
    AceBox,
    AceDrying,
    AceSlot,
    Fans,
    Job,
    Light,
    Position,
    PrinterState,
    Report,
    ReportCode,
    Temperatures,
    parse_message,
)

__version__ = "0.1.0"

__all__ = [
    "AceBox",
    "AceDrying",
    "AceSlot",
    "AnycubicLanClient",
    "AnycubicLanError",
    "BrokerCredentials",
    "DiscoveryInfo",
    "Fans",
    "InvalidResponseError",
    "Job",
    "LanModeDisabledError",
    "Light",
    "NoActiveJobError",
    "NotConnectedError",
    "Position",
    "PrintStatus",
    "PrinterConnectionInfo",
    "PrinterState",
    "PrinterStatus",
    "PrinterUnreachableError",
    "Report",
    "ReportCode",
    "ReportKind",
    "RequestRejectedError",
    "SpeedMode",
    "Temperatures",
    "UnsupportedPrinterError",
    "__version__",
    "fetch_discovery",
    "handshake",
    "parse_message",
    "printer_model_name",
]
