"""Exceptions raised by anycubic-lan.

Every exception derives from :class:`AnycubicLanError`, so callers that do not
care about the reason can catch that one class.
"""

from __future__ import annotations


class AnycubicLanError(Exception):
    """Base class for every error raised by this library."""


class PrinterUnreachableError(AnycubicLanError):
    """The printer did not answer: wrong address, switched off or asleep.

    Raised for connection refused, timeouts and DNS failures, both during the
    handshake (PROTOCOL.md §2) and when opening the MQTT connection.
    """


class LanModeDisabledError(AnycubicLanError):
    """The printer answered, but LAN Mode is switched off (``ctrlType: cloud``)."""


class UnsupportedPrinterError(AnycubicLanError):
    """The printer answered with a discovery document this library cannot use.

    Typically an older model (Kobra 2 and earlier) whose document lacks
    ``token``, ``ctrlInfoUrl`` or ``modelId``.
    """


class InvalidResponseError(AnycubicLanError):
    """The printer answered with something that could not be understood."""


class RequestRejectedError(InvalidResponseError):
    """The printer understood the request and refused it.

    ``code`` and ``message`` carry what the printer said, when it said
    anything.
    """

    def __init__(
        self, message: str, *, code: object = None, printer_message: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.printer_message = printer_message


class NotConnectedError(AnycubicLanError):
    """A query or command was attempted while the MQTT connection is down."""


class NoActiveJobError(AnycubicLanError):
    """A job command (pause, resume, stop) was attempted with no known job."""
