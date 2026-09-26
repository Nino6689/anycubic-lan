"""Client tests with a fake paho-mqtt client; no network."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import ssl
import threading
from types import SimpleNamespace
from typing import Any, ClassVar

import paho.mqtt.client as mqtt
import pytest

from anycubic_lan import (
    AnycubicLanClient,
    NoActiveJobError,
    NotConnectedError,
    PrinterUnreachableError,
    RequestRejectedError,
)
from anycubic_lan.client import (
    build_command,
    build_query,
    command_topic,
    job_command_data,
    light_command_data,
    report_topic_filter,
)
from anycubic_lan.handshake import (
    PrinterConnectionInfo,
    parse_credentials,
    parse_discovery,
)
from anycubic_lan.models import PrinterStatus, ReportKind

from .payloads import CREDENTIALS, DISCOVERY, INFO_IDLE, PROJECT, info_with, message

PREFIX = "anycubic/anycubicCloud/v1"
REPORT = f"{PREFIX}/printer/public/20025/DEVICE1234"
WEB = f"{PREFIX}/web/printer/20025/DEVICE1234"


class ReasonCode:
    def __init__(self, failure: bool = False, name: str = "Success") -> None:
        self.is_failure = failure
        self.name = name

    def __str__(self) -> str:
        return self.name


class FakeMqtt:
    """Records what the library does with paho and fires callbacks on a thread."""

    instances: ClassVar[list[FakeMqtt]] = []
    connect_error: ClassVar[BaseException | None] = None
    connack: ClassVar[ReasonCode | None] = ReasonCode()
    publish_rc: ClassVar[int] = mqtt.MQTT_ERR_SUCCESS

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.subscribed: list[str] = []
        self.connected_to: tuple[str, int, int] | None = None
        self.disconnected = False
        self.stopped = False
        self.tls_insecure = False
        self.connect_timeout = 5.0
        self.on_connect: Any = None
        self.on_disconnect: Any = None
        self.on_message: Any = None
        FakeMqtt.instances.append(self)

    def username_pw_set(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def tls_set_context(self, context: ssl.SSLContext) -> None:
        self.tls_context = context

    def tls_insecure_set(self, value: bool) -> None:
        self.tls_insecure = value

    def reconnect_delay_set(self, min_delay: int, max_delay: int) -> None:
        self.reconnect_delay = (min_delay, max_delay)

    def connect(self, host: str, port: int, keepalive: int) -> None:
        if FakeMqtt.connect_error is not None:
            raise FakeMqtt.connect_error
        self.connected_to = (host, port, keepalive)

    def loop_start(self) -> None:
        if FakeMqtt.connack is not None:
            self.in_thread(self.on_connect, self, None, None, FakeMqtt.connack, None)

    def loop_stop(self) -> None:
        self.stopped = True

    def disconnect(self) -> None:
        self.disconnected = True

    def subscribe(self, topic: str) -> None:
        self.subscribed.append(topic)

    def publish(self, topic: str, payload: str) -> Any:
        self.published.append((topic, json.loads(payload)))
        return SimpleNamespace(rc=FakeMqtt.publish_rc)

    # -- helpers for tests --------------------------------------------------

    @staticmethod
    def in_thread(target: Any, *args: Any) -> None:
        thread = threading.Thread(target=target, args=args)
        thread.start()
        thread.join()

    def fire_connect(self, failure: bool = False) -> None:
        self.in_thread(self.on_connect, self, None, None, ReasonCode(failure), None)

    def fire_disconnect(self) -> None:
        self.in_thread(
            self.on_disconnect, self, None, None, ReasonCode(True, "Unspecified"), None
        )

    def fire_message(self, payload: Any, topic: str = f"{REPORT}/info/report") -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.in_thread(
            self.on_message, self, None, SimpleNamespace(topic=topic, payload=data)
        )


@pytest.fixture(autouse=True)
def fake_mqtt(monkeypatch: pytest.MonkeyPatch) -> type[FakeMqtt]:
    FakeMqtt.instances = []
    FakeMqtt.connect_error = None
    FakeMqtt.connack = ReasonCode()
    FakeMqtt.publish_rc = mqtt.MQTT_ERR_SUCCESS
    monkeypatch.setattr("anycubic_lan.client.mqtt.Client", FakeMqtt)
    return FakeMqtt


def connection() -> PrinterConnectionInfo:
    return PrinterConnectionInfo(
        host="10.0.66.28",
        discovery=parse_discovery(DISCOVERY),
        credentials=parse_credentials(json.dumps(CREDENTIALS).encode()),
    )


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def connected_client(**kwargs: Any) -> tuple[AnycubicLanClient, FakeMqtt]:
    client = AnycubicLanClient(connection(), **kwargs)
    await client.connect()
    fake = FakeMqtt.instances[-1]
    fake.published.clear()
    return client, fake


# -- pure helpers -------------------------------------------------------------


def test_topics() -> None:
    assert report_topic_filter(20025, "DEVICE1234") == f"{REPORT}/#"
    assert command_topic(20025, "DEVICE1234", "tempature") == f"{WEB}/tempature"


@pytest.mark.parametrize(
    ("kind", "action"),
    [
        (ReportKind.INFO, "query"),
        (ReportKind.TEMPERATURE, "query"),
        (ReportKind.FAN, "query"),
        (ReportKind.LIGHT, "query"),
        (ReportKind.MULTI_COLOR_BOX, "getInfo"),
        (ReportKind.PRINT, "query"),
        (ReportKind.AI_SETTINGS, "query"),
        (ReportKind.PERIPHERALS, "query"),
        (ReportKind.AXIS, "query"),
        (ReportKind.EXTERNAL_FILAMENT_BOX, "query"),
    ],
)
def test_query_envelope(kind: ReportKind, action: str) -> None:
    assert build_query(kind) == {"type": kind.value, "action": action, "data": {}}


def test_query_type_spellings() -> None:
    assert build_query(ReportKind.TEMPERATURE)["type"] == "tempature"
    assert build_query(ReportKind.PERIPHERALS)["type"] == "peripherie"
    assert build_query(ReportKind.MULTI_COLOR_BOX) == {
        "type": "multiColorBox",
        "action": "getInfo",
        "data": {},
    }


def test_command_envelope() -> None:
    command = build_command(
        ReportKind.LIGHT,
        "control",
        {"type": 2, "status": 1, "brightness": 100},
        timestamp=1754640000000,
        msgid="8f1c",
    )
    assert command == {
        "type": "light",
        "action": "control",
        "timestamp": 1754640000000,
        "msgid": "8f1c",
        "data": {"type": 2, "status": 1, "brightness": 100},
    }


def test_command_envelope_defaults() -> None:
    command = build_command(ReportKind.AXIS, "turnOff", None)
    assert command["data"] == {}
    assert isinstance(command["timestamp"], int)
    assert command["timestamp"] > 1_700_000_000_000  # milliseconds
    assert re.fullmatch(r"[0-9a-f-]{36}", command["msgid"])
    assert build_command(ReportKind.AXIS, "turnOff", None)["msgid"] != command["msgid"]


def test_job_command_taskid_is_string() -> None:
    assert job_command_data(614707220) == {"taskid": "614707220"}


def test_light_command_data() -> None:
    assert light_command_data(True, 100) == {"type": 2, "status": 1, "brightness": 100}
    assert light_command_data(False, 0, 3) == {"type": 3, "status": 0, "brightness": 0}
    for bad in (-1, 101):
        with pytest.raises(ValueError, match="brightness"):
            light_command_data(True, bad)


# -- connect ------------------------------------------------------------------


async def test_connect_configures_paho_and_queries() -> None:
    client = AnycubicLanClient(connection(), client_id="ha-0123456789ab")
    assert not client.is_connected
    await client.connect()
    fake = FakeMqtt.instances[-1]
    assert client.is_connected
    assert client.connection.device_id == "DEVICE1234"
    assert fake.kwargs["client_id"] == "ha-0123456789ab"
    assert fake.kwargs["protocol"] == mqtt.MQTTv311
    assert fake.credentials == ("printer-user", "printer-pass")
    assert fake.tls_context.check_hostname is False
    assert fake.tls_context.verify_mode == ssl.CERT_NONE
    assert fake.tls_insecure is True
    assert fake.connect_timeout == 15.0
    assert fake.connected_to == ("10.0.66.28", 9883, 60)
    assert fake.subscribed == [f"{REPORT}/#"]
    assert client.report_topic == f"{REPORT}/#"
    topics = [topic for topic, _ in fake.published]
    assert topics == [f"{WEB}/{kind.value}" for kind in ReportKind]
    assert all(
        payload == build_query(ReportKind(payload["type"]))
        for _, payload in fake.published
    )
    await client.connect()  # already connected: no second paho client
    assert len(FakeMqtt.instances) == 1
    await client.disconnect()


async def test_default_client_id() -> None:
    client, fake = await connected_client()
    assert re.fullmatch(r"anycubic-lan-[0-9a-f]{12}", fake.kwargs["client_id"])
    await client.disconnect()


async def test_connect_refused_credentials() -> None:
    FakeMqtt.connack = ReasonCode(True, "Not authorized")
    client = AnycubicLanClient(connection())
    with pytest.raises(RequestRejectedError, match="Not authorized"):
        await client.connect()
    fake = FakeMqtt.instances[-1]
    assert fake.stopped
    assert fake.disconnected
    assert not client.is_connected
    assert fake.subscribed == []


async def test_connect_unreachable() -> None:
    FakeMqtt.connect_error = ConnectionRefusedError("refused")
    client = AnycubicLanClient(connection())
    with pytest.raises(PrinterUnreachableError):
        await client.connect()
    assert not client.is_connected


async def test_connect_timeout() -> None:
    FakeMqtt.connack = None
    client = AnycubicLanClient(connection(), connect_timeout=0.05)
    with pytest.raises(PrinterUnreachableError, match="did not answer"):
        await client.connect()
    assert FakeMqtt.instances[-1].stopped


async def test_connect_dropped_before_connack() -> None:
    FakeMqtt.connack = None
    client = AnycubicLanClient(connection())
    task = asyncio.create_task(client.connect())
    await settle()
    FakeMqtt.instances[-1].fire_disconnect()
    with pytest.raises(PrinterUnreachableError, match="closed"):
        await task


async def test_connect_cancelled() -> None:
    FakeMqtt.connack = None
    client = AnycubicLanClient(connection())
    task = asyncio.create_task(client.connect())
    await settle()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert FakeMqtt.instances[-1].stopped


# -- state updates ------------------------------------------------------------


async def test_state_updates_reach_listener_on_loop_thread() -> None:
    client, fake = await connected_client()
    seen: list[tuple[PrinterStatus, int]] = []
    remove = client.add_state_listener(
        lambda state: seen.append((state.status, threading.get_ident()))
    )
    fake.fire_message(INFO_IDLE)
    await settle()
    assert seen == [(PrinterStatus.IDLE, threading.get_ident())]
    fake.fire_message(info_with(state="busy", project=PROJECT))
    await settle()
    assert seen[-1][0] is PrinterStatus.PRINTING
    assert client.state.job is not None
    remove()
    remove()  # removing twice is harmless
    fake.fire_message(INFO_IDLE)
    await settle()
    assert len(seen) == 2
    assert client.state.job is None
    await client.disconnect()


async def test_ignored_messages_do_not_notify() -> None:
    client, fake = await connected_client()
    seen: list[Any] = []
    client.add_state_listener(seen.append)
    fake.fire_message(b"garbage")
    fake.fire_message({"msgid": ""})
    fake.fire_message({"type": "", "data": {}})
    await settle()
    assert seen == []
    await client.disconnect()


async def test_listener_errors_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    client, fake = await connected_client()

    def broken(_: Any) -> None:
        raise RuntimeError("boom")

    seen: list[Any] = []
    client.add_state_listener(broken)
    client.add_state_listener(seen.append)
    with caplog.at_level(logging.ERROR):
        fake.fire_message(INFO_IDLE)
        await settle()
    assert len(seen) == 1
    assert "Error in state listener" in caplog.text
    await client.disconnect()


# -- connection lost / restored -----------------------------------------------


async def test_connection_lost_and_restored_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, fake = await connected_client()
    events: list[bool] = []
    client.add_connection_listener(events.append)

    with caplog.at_level(logging.INFO):
        fake.fire_disconnect()
        fake.fire_disconnect()
        await settle()
        assert events == [False]
        assert not client.is_connected
        with pytest.raises(NotConnectedError):
            await client.query_all()

        fake.fire_connect(failure=True)  # retries with stale credentials
        await settle()
        assert events == [False]

        fake.fire_connect()
        await settle()
        assert events == [False, True]
        assert client.is_connected
    assert caplog.text.count("lost") == 1
    assert caplog.text.count("restored") == 1
    # Resubscribed and re-queried after the reconnect.
    assert fake.subscribed == [f"{REPORT}/#", f"{REPORT}/#"]
    assert len(fake.published) == len(ReportKind)
    await client.disconnect()


async def test_connection_listener_errors_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, fake = await connected_client()

    def broken(_: bool) -> None:
        raise RuntimeError("boom")

    remove = client.add_connection_listener(broken)
    with caplog.at_level(logging.ERROR):
        fake.fire_disconnect()
        await settle()
    assert "Error in connection listener" in caplog.text
    remove()
    await client.disconnect()


async def test_disconnect_is_clean() -> None:
    client, fake = await connected_client()
    events: list[bool] = []
    client.add_connection_listener(events.append)
    await client.disconnect()
    assert fake.disconnected
    assert fake.stopped
    assert not client.is_connected
    fake.fire_disconnect()  # paho reports the disconnect we asked for
    fake.fire_connect()  # a late CONNACK after closing is ignored
    await settle()
    assert events == []
    assert not client.is_connected
    await client.disconnect()  # second call is a no-op
    with pytest.raises(NotConnectedError):
        await client.query(ReportKind.INFO)


async def test_callbacks_after_loop_gone_are_dropped() -> None:
    client = AnycubicLanClient(connection())
    # Never connected: no loop to hand to.
    client._on_message(None, None, SimpleNamespace(topic="t", payload=b"{}"))  # type: ignore[arg-type]
    closed = asyncio.new_event_loop()
    closed.close()
    client._loop = closed
    client._on_message(None, None, SimpleNamespace(topic="t", payload=b"{}"))  # type: ignore[arg-type]


# -- queries and commands -----------------------------------------------------


async def test_query_and_query_all() -> None:
    client, fake = await connected_client()
    await client.query(ReportKind.MULTI_COLOR_BOX)
    assert fake.published == [
        (
            f"{WEB}/multiColorBox",
            {"type": "multiColorBox", "action": "getInfo", "data": {}},
        )
    ]
    fake.published.clear()
    await client.query_all()
    assert [topic.rsplit("/", 1)[1] for topic, _ in fake.published] == [
        "info",
        "tempature",
        "fan",
        "light",
        "multiColorBox",
        "print",
        "aiSettings",
        "peripherie",
        "axis",
        "extfilbox",
    ]
    await client.disconnect()


async def test_publish_failure() -> None:
    client, _ = await connected_client()
    FakeMqtt.publish_rc = mqtt.MQTT_ERR_NO_CONN
    with pytest.raises(NotConnectedError, match="rc="):
        await client.query_all()
    await client.disconnect()


async def test_queries_on_connect_tolerate_publish_failure() -> None:
    FakeMqtt.publish_rc = mqtt.MQTT_ERR_NO_CONN
    client = AnycubicLanClient(connection())
    await client.connect()
    assert client.is_connected
    await client.disconnect()


async def test_job_commands_need_a_job() -> None:
    client, fake = await connected_client()
    for command in (client.pause, client.resume, client.stop):
        with pytest.raises(NoActiveJobError):
            await command()
    fake.fire_message(info_with(project={"progress": 3}))  # job without task id
    await settle()
    with pytest.raises(NoActiveJobError):
        await client.pause()
    assert fake.published == []
    await client.disconnect()


@pytest.mark.parametrize("action", ["pause", "resume", "stop"])
async def test_job_commands(action: str) -> None:
    client, fake = await connected_client()
    fake.fire_message(info_with(state="busy", project=PROJECT))
    await settle()
    msgid = await getattr(client, action)()
    ((topic, payload),) = fake.published
    assert topic == f"{WEB}/print"
    assert payload["type"] == "print"
    assert payload["action"] == action
    assert payload["data"] == {"taskid": "614707220"}
    assert payload["msgid"] == msgid
    assert isinstance(payload["timestamp"], int)
    await client.disconnect()


async def test_commands_when_not_connected() -> None:
    client = AnycubicLanClient(connection())
    with pytest.raises(NotConnectedError):
        await client.light_on()


async def test_light_commands() -> None:
    client, fake = await connected_client()

    async def sent(coro: Any) -> dict[str, Any]:
        fake.published.clear()
        await coro
        ((topic, payload),) = fake.published
        assert topic == f"{WEB}/light"
        assert payload["type"] == "light"
        assert payload["action"] == "control"
        return dict(payload["data"])

    assert await sent(client.light_on()) == {"type": 2, "status": 1, "brightness": 100}
    assert await sent(client.light_off()) == {"type": 2, "status": 0, "brightness": 0}

    fake.fire_message(
        message("light", {"lights": [{"type": 2, "status": 1, "brightness": 40}]}),
        topic=f"{REPORT}/light/report",
    )
    await settle()
    assert await sent(client.light_off()) == {"type": 2, "status": 0, "brightness": 40}
    assert await sent(client.light_on()) == {"type": 2, "status": 1, "brightness": 40}
    assert await sent(client.light_on(75)) == {"type": 2, "status": 1, "brightness": 75}
    assert await sent(client.set_light_brightness(20)) == {
        "type": 2,
        "status": 1,
        "brightness": 20,
    }
    assert await sent(client.set_light_brightness(0)) == {
        "type": 2,
        "status": 0,
        "brightness": 0,
    }
    assert await sent(client.set_light(True, light_type=3)) == {
        "type": 3,
        "status": 1,
        "brightness": 100,
    }
    with pytest.raises(ValueError, match="brightness"):
        await client.set_light_brightness(150)
    await client.disconnect()


async def test_send_command_raw() -> None:
    client, fake = await connected_client()
    msgid = await client.send_command(ReportKind.AXIS, "turnOff")
    ((topic, payload),) = fake.published
    assert topic == f"{WEB}/axis"
    assert payload["msgid"] == msgid
    assert payload["data"] == {}
    await client.disconnect()
