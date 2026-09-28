"""Async MQTT client for a printer in LAN Mode (PROTOCOL.md §4, §7, §10).

paho-mqtt runs its network loop in its own thread. Every callback from that
thread is handed to the asyncio loop with ``call_soon_threadsafe``; state is
only ever read and written on the asyncio loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import ssl
import time
import uuid
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .exceptions import (
    NoActiveJobError,
    NotConnectedError,
    PrinterUnreachableError,
    RequestRejectedError,
)
from .models import DEFAULT_LIGHT_TYPE, QUERY_ACTIONS, TOPIC_PREFIX, ReportKind
from .reports import PrinterState, parse_message

if TYPE_CHECKING:
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode

    from .handshake import PrinterConnectionInfo

_LOGGER = logging.getLogger(__name__)

DEFAULT_KEEPALIVE = 60
DEFAULT_CONNECT_TIMEOUT = 15.0

type StateCallback = Callable[[PrinterState], None]
type ConnectionCallback = Callable[[bool], None]


# --------------------------------------------------------------------------
# Topics and envelopes (pure)
# --------------------------------------------------------------------------


def report_topic_filter(model_id: int, device_id: str) -> str:
    """Subscription filter for every report from one printer."""
    return f"{TOPIC_PREFIX}/printer/public/{model_id}/{device_id}/#"


def command_topic(model_id: int, device_id: str, kind: str) -> str:
    """Topic for queries and commands of one report kind."""
    return f"{TOPIC_PREFIX}/web/printer/{model_id}/{device_id}/{kind}"


def build_query(kind: ReportKind) -> dict[str, Any]:
    """Query envelope (PROTOCOL.md §7.1)."""
    return {"type": kind.value, "action": QUERY_ACTIONS[kind], "data": {}}


def build_command(
    kind: ReportKind,
    action: str,
    data: Mapping[str, Any] | None,
    *,
    timestamp: int | None = None,
    msgid: str | None = None,
) -> dict[str, Any]:
    """Command envelope with a millisecond timestamp and fresh msgid (§7.2)."""
    return {
        "type": kind.value,
        "action": action,
        "timestamp": timestamp if timestamp is not None else int(time.time() * 1000),
        "msgid": msgid if msgid is not None else str(uuid.uuid4()),
        "data": dict(data) if data is not None else {},
    }


def job_command_data(task_id: int) -> dict[str, str]:
    """``data`` of pause/resume/stop: the task id as a string (§7.2)."""
    return {"taskid": str(task_id)}


def light_command_data(
    on: bool, brightness: int, light_type: int = DEFAULT_LIGHT_TYPE
) -> dict[str, int]:
    """``data`` of a light ``control`` command (§7.2)."""
    if not 0 <= brightness <= 100:
        raise ValueError("brightness must be between 0 and 100")
    return {"type": light_type, "status": 1 if on else 0, "brightness": brightness}


def _tls_context() -> ssl.SSLContext:
    # PROTOCOL.md §4: the broker's certificate is self-signed for an address
    # that varies per unit, so there is nothing to verify. The link is still
    # encrypted. No CA bundle is loaded, so building this does not block.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class AnycubicLanClient:
    """One MQTT connection to one printer.

    Usage::

        client = AnycubicLanClient(connection_info)
        client.add_state_listener(on_state)
        await client.connect()
        await client.query_all()
        ...
        await client.disconnect()

    After :meth:`connect` succeeds, paho-mqtt reconnects on its own with the
    same credentials. Connection listeners are told ``False`` once when the
    connection drops and ``True`` once when it comes back. Credentials rotate
    when the printer restarts (PROTOCOL.md §10); if the connection does not
    come back, disconnect, run the handshake again and build a new client.
    """

    def __init__(
        self,
        connection: PrinterConnectionInfo,
        *,
        client_id: str | None = None,
        keepalive: int = DEFAULT_KEEPALIVE,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        self._connection = connection
        self._client_id = client_id or f"anycubic-lan-{secrets.token_hex(6)}"
        self._keepalive = keepalive
        self._connect_timeout = connect_timeout
        self._state = PrinterState()
        self._state_listeners: list[StateCallback] = []
        self._connection_listeners: list[ConnectionCallback] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mqtt: mqtt.Client | None = None
        self._connack: asyncio.Future[None] | None = None
        self._connected = False
        self._closing = False

    # -- properties ---------------------------------------------------------

    @property
    def connection(self) -> PrinterConnectionInfo:
        return self._connection

    @property
    def state(self) -> PrinterState:
        """The latest merged state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def report_topic(self) -> str:
        return report_topic_filter(
            self._connection.model_id, self._connection.device_id
        )

    def command_topic(self, kind: ReportKind) -> str:
        return command_topic(
            self._connection.model_id, self._connection.device_id, kind.value
        )

    # -- listeners ----------------------------------------------------------

    def add_state_listener(self, callback: StateCallback) -> Callable[[], None]:
        """Call ``callback(state)`` on the event loop after every report.

        Returns a function that removes the listener.
        """
        self._state_listeners.append(callback)
        return lambda: _discard(self._state_listeners, callback)

    def add_connection_listener(
        self, callback: ConnectionCallback
    ) -> Callable[[], None]:
        """Call ``callback(False)`` when the connection is lost and
        ``callback(True)`` when it is restored, once per transition.

        The first connection made by :meth:`connect` is not reported: its
        success or failure is the outcome of that call.

        Returns a function that removes the listener.
        """
        self._connection_listeners.append(callback)
        return lambda: _discard(self._connection_listeners, callback)

    # -- connection ---------------------------------------------------------

    def _create_mqtt_client(self) -> mqtt.Client:
        credentials = self._connection.credentials
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
            protocol=mqtt.MQTTv311,
        )
        client.username_pw_set(credentials.username, credentials.password)
        # TLS is always used, whatever the broker URL's scheme: only
        # "mqtts://" on port 9883 has been observed (Q7 in docs/QUESTIONS.md).
        client.tls_set_context(_tls_context())
        client.tls_insecure_set(True)
        client.connect_timeout = self._connect_timeout
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    async def connect(self) -> None:
        """Connect, subscribe to reports and send every query.

        Raises :class:`PrinterUnreachableError` when the broker does not
        answer in time and :class:`RequestRejectedError` when it refuses the
        credentials.
        """
        if self._mqtt is not None:
            return
        loop = self._loop = asyncio.get_running_loop()
        credentials = self._connection.credentials
        self._closing = False
        client = self._mqtt = self._create_mqtt_client()
        self._connack = loop.create_future()
        try:
            async with asyncio.timeout(self._connect_timeout):
                await loop.run_in_executor(
                    None,
                    client.connect,
                    credentials.host,
                    credentials.port,
                    self._keepalive,
                )
                client.loop_start()
                await self._connack
        except TimeoutError as err:
            await self._teardown(client)
            raise PrinterUnreachableError("MQTT broker did not answer") from err
        except OSError as err:
            await self._teardown(client)
            raise PrinterUnreachableError(f"MQTT broker unreachable: {err}") from err
        except BaseException:
            await self._teardown(client)
            raise
        finally:
            self._connack = None

    async def disconnect(self) -> None:
        """Close the connection. Listeners are not told about this."""
        if (client := self._mqtt) is not None:
            await self._teardown(client)

    async def _teardown(self, client: mqtt.Client) -> None:
        self._closing = True
        self._mqtt = None
        self._connected = False
        client.disconnect()
        await asyncio.get_running_loop().run_in_executor(None, client.loop_stop)

    # -- paho callbacks (paho's thread) -------------------------------------

    def _dispatch(self, callback: Callable[..., None], *args: Any) -> None:
        if (loop := self._loop) is None:
            return
        try:
            loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:  # loop closed while paho was still running
            _LOGGER.debug("Event loop closed; dropping MQTT callback")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        failed = reason_code.is_failure
        if not failed:
            # Subscribing here makes paho resubscribe after every reconnect.
            client.subscribe(self.report_topic)
        self._dispatch(self._handle_connect, failed, str(reason_code))

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.DisconnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        self._dispatch(self._handle_disconnect, str(reason_code))

    def _on_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        self._dispatch(self._handle_message, message.topic, bytes(message.payload))

    # -- handlers (event loop) ----------------------------------------------

    def _handle_connect(self, failed: bool, reason: str) -> None:
        connack = self._connack
        if failed:
            if connack is not None and not connack.done():
                connack.set_exception(
                    RequestRejectedError(
                        f"MQTT broker refused the connection: {reason}"
                    )
                )
            return
        if self._closing:
            return
        was_lost = connack is None and not self._connected
        self._connected = True
        if connack is not None and not connack.done():
            connack.set_result(None)
        if was_lost:
            _LOGGER.info("Connection to printer %s restored", self._connection.host)
            self._notify_connection(True)
        self._send_queries()

    def _handle_disconnect(self, reason: str) -> None:
        if self._closing:
            return
        connack = self._connack
        if connack is not None and not connack.done():
            connack.set_exception(
                PrinterUnreachableError(f"MQTT connection closed: {reason}")
            )
        if self._connected:
            self._connected = False
            _LOGGER.warning(
                "Connection to printer %s lost: %s", self._connection.host, reason
            )
            self._notify_connection(False)

    def _handle_message(self, topic: str, payload: bytes) -> None:
        report = parse_message(payload, topic)
        if report is None:
            return
        self._state = self._state.apply(report)
        for callback in list(self._state_listeners):
            try:
                callback(self._state)
            except Exception:
                _LOGGER.exception("Error in state listener")

    def _notify_connection(self, connected: bool) -> None:
        for callback in list(self._connection_listeners):
            try:
                callback(connected)
            except Exception:
                _LOGGER.exception("Error in connection listener")

    # -- publishing ---------------------------------------------------------

    def _publish(self, kind: ReportKind, payload: Mapping[str, Any]) -> None:
        client = self._mqtt
        if client is None or not self._connected:
            raise NotConnectedError("Not connected to the printer")
        # QoS 0 for publishing and subscribing, as used against real hardware
        # (Q8 in docs/QUESTIONS.md).
        info = client.publish(
            self.command_topic(kind), json.dumps(payload, separators=(",", ":"))
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise NotConnectedError(f"Publish failed (rc={info.rc})")

    def _send_queries(self) -> None:
        try:
            for kind in ReportKind:
                self._publish(kind, build_query(kind))
        except NotConnectedError:
            _LOGGER.debug("Connection dropped while sending queries")

    async def query(self, kind: ReportKind) -> None:
        """Ask the printer for one kind of report."""
        self._publish(kind, build_query(kind))

    async def query_all(self) -> None:
        """Ask the printer for every kind of report (PROTOCOL.md §7.1)."""
        for kind in ReportKind:
            self._publish(kind, build_query(kind))

    async def send_command(
        self, kind: ReportKind, action: str, data: Mapping[str, Any] | None = None
    ) -> str:
        """Publish a raw command; returns its ``msgid``."""
        payload = build_command(kind, action, data)
        self._publish(kind, payload)
        return str(payload["msgid"])

    # -- job commands -------------------------------------------------------

    def _current_task_id(self) -> int:
        job = self._state.job
        if job is None or job.task_id is None:
            raise NoActiveJobError("No current print job")
        return job.task_id

    async def _job_command(self, action: str) -> str:
        return await self.send_command(
            ReportKind.PRINT, action, job_command_data(self._current_task_id())
        )

    async def pause(self) -> str:
        """Pause the current job."""
        return await self._job_command("pause")

    async def resume(self) -> str:
        """Resume the current job."""
        return await self._job_command("resume")

    async def stop(self) -> str:
        """Stop (cancel) the current job."""
        return await self._job_command("stop")

    # -- light --------------------------------------------------------------

    async def set_light(
        self,
        on: bool,
        brightness: int | None = None,
        *,
        light_type: int = DEFAULT_LIGHT_TYPE,
    ) -> str:
        """Switch a light and optionally set its brightness (0-100).

        Switching off always sends brightness 0. Switching on sends
        ``brightness``, or 100 when none is given: the printer is not relied
        on to remember a previous brightness (Q9 in docs/QUESTIONS.md).
        """
        if not on:
            brightness = 0
        elif brightness is None:
            brightness = 100
        return await self.send_command(
            ReportKind.LIGHT, "control", light_command_data(on, brightness, light_type)
        )

    async def light_on(self, brightness: int | None = None) -> str:
        return await self.set_light(True, brightness)

    async def light_off(self) -> str:
        return await self.set_light(False)

    async def set_light_brightness(self, brightness: int) -> str:
        """Set the brightness; 0 switches the light off."""
        return await self.set_light(brightness > 0, brightness)


def _discard[T](items: list[T], item: T) -> None:
    if item in items:
        items.remove(item)
