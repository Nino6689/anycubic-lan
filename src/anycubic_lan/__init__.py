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
    FeedSource,
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
    Envelope,
    ExternalFilamentBoxReport,
    Fans,
    FilamentFeed,
    Job,
    Light,
    MultiColorBoxReport,
    Position,
    PrinterState,
    PrintReport,
    Report,
    ReportCode,
    Temperatures,
    current_filament,
    filament_feed,
    parse_message,
)

__version__ = "0.1.1"

__all__ = [
    "AceBox",
    "AceDrying",
    "AceSlot",
    "AnycubicLanClient",
    "AnycubicLanError",
    "BrokerCredentials",
    "DiscoveryInfo",
    "Envelope",
    "ExternalFilamentBoxReport",
    "Fans",
    "FeedSource",
    "FilamentFeed",
    "InvalidResponseError",
    "Job",
    "LanModeDisabledError",
    "Light",
    "MultiColorBoxReport",
    "NoActiveJobError",
    "NotConnectedError",
    "Position",
    "PrintReport",
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
    "current_filament",
    "fetch_discovery",
    "filament_feed",
    "handshake",
    "parse_message",
    "printer_model_name",
]
