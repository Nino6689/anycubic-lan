"""Handshake tests (PROTOCOL.md §2, §3) with a fake HTTP layer."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, cast

import aiohttp
import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from anycubic_lan import (
    InvalidResponseError,
    LanModeDisabledError,
    PrinterUnreachableError,
    RequestRejectedError,
    UnsupportedPrinterError,
    handshake,
)
from anycubic_lan.handshake import (
    BrokerCredentials,
    DiscoveryInfo,
    build_iv,
    build_signature,
    control_url,
    decrypt_info,
    fetch_discovery,
    mac_from_usn,
    parse_broker_url,
    parse_credentials,
    parse_discovery,
    random_did,
    random_nonce,
)

from .payloads import CREDENTIALS, DISCOVERY

if TYPE_CHECKING:
    from yarl import URL

TOKEN = DISCOVERY["token"]
IV_SOURCE = "abcdefghijklmnopqrstuvwxyz"


def encrypt(plaintext: bytes, key: bytes, iv: bytes) -> str:
    """Encrypt with the parameters stated in PROTOCOL.md §3.5."""
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def control_response(
    credentials: Any = CREDENTIALS, *, iv_source: str = IV_SOURCE, key: str = TOKEN
) -> dict[str, Any]:
    plaintext = (
        credentials
        if isinstance(credentials, bytes)
        else json.dumps(credentials).encode()
    )
    iv = iv_source.encode()[:16].ljust(16, b"\x00")
    info = encrypt(plaintext, key[16:32].encode(), iv)
    return {"code": 200, "data": {"info": info, "token": iv_source}}


# -- fake HTTP layer ----------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeSession:
    """Stands in for aiohttp.ClientSession.request()."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, URL, aiohttp.ClientTimeout]] = []

    def request(self, method: str, url: URL, *, timeout: aiohttp.ClientTimeout) -> Any:
        self.calls.append((method, url, timeout))
        answer = self.routes[method]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, FakeResponse):
            return answer
        body = answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        return FakeResponse(200, body)


def session(get: Any = DISCOVERY, post: Any = None) -> Any:
    return cast(
        "aiohttp.ClientSession",
        FakeSession(
            {"GET": get, "POST": post if post is not None else control_response()}
        ),
    )


# -- pure pieces ----------------------------------------------------------------


def test_signature_matches_stated_rule() -> None:
    signing_key = "0123456789abcdef"
    ts = 1754640000000
    nonce = "aB3xY9"
    # Built independently: MD5 hex of the key, then MD5 hex of key-hash + ts + nonce.
    first = hashlib.md5(b"0123456789abcdef", usedforsecurity=False).hexdigest()
    expected = hashlib.md5(
        f"{first}1754640000000aB3xY9".encode(), usedforsecurity=False
    ).hexdigest()
    assert build_signature(signing_key, ts, nonce) == expected
    assert re.fullmatch(r"[0-9a-f]{32}", expected)


def test_control_url_parameter_order() -> None:
    url = control_url(
        TOKEN, "http://10.0.66.28:18910/ctrl", 1754640000000, "aB3xY9", "D" * 32
    )
    sign = build_signature(TOKEN[:16], 1754640000000, "aB3xY9")
    assert url == (
        "http://10.0.66.28:18910/ctrl?ts=1754640000000&nonce=aB3xY9"
        f"&sign={sign}&did={'D' * 32}"
    )
    with_query = control_url(TOKEN, "http://h/ctrl?x=1", 1, "n", "d")
    assert with_query.startswith("http://h/ctrl?x=1&ts=1&")


def test_random_nonce_and_did() -> None:
    assert re.fullmatch(r"[A-Za-z0-9]{6}", random_nonce())
    assert re.fullmatch(r"[A-Z0-9]{32}", random_did())


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("short", b"short" + b"\x00" * 11),
        ("", b"\x00" * 16),
        ("exactly16bytes!!", b"exactly16bytes!!"),
        ("this is longer than sixteen", b"this is longer t"),
    ],
)
def test_iv_padding_and_truncation(source: str, expected: bytes) -> None:
    assert build_iv(source) == expected
    assert len(build_iv(source)) == 16


@pytest.mark.parametrize("iv_source", ["short", IV_SOURCE, "exactly16bytes!!"])
def test_decrypt_round_trip(iv_source: str) -> None:
    response = control_response(iv_source=iv_source)
    plaintext = decrypt_info(response["data"]["info"], iv_source, TOKEN[16:32].encode())
    assert json.loads(plaintext) == CREDENTIALS


def test_decrypt_wrong_key() -> None:
    response = control_response()
    with pytest.raises(InvalidResponseError):
        # A wrong key gives a padding error or garbage; either is a bad response.
        parse_credentials(decrypt_info(response["data"]["info"], IV_SOURCE, b"W" * 16))


@pytest.mark.parametrize(
    "info", ["***not base64***", base64.b64encode(b"short").decode()]
)
def test_decrypt_bad_ciphertext(info: str) -> None:
    with pytest.raises(InvalidResponseError):
        decrypt_info(info, IV_SOURCE, TOKEN[16:32].encode())


def test_mac_from_usn() -> None:
    assert mac_from_usn("uuid:fdm:A4-E8-8D-80-54-C8") == "a4:e8:8d:80:54:c8"
    assert mac_from_usn("uuid:fdm:a4e88d8054c8") == "a4:e8:8d:80:54:c8"
    assert mac_from_usn("uuid:fdm:nothing") is None


def test_parse_discovery() -> None:
    info = parse_discovery(DISCOVERY)
    assert info.token == TOKEN
    assert info.ctrl_info_url == "http://10.0.66.28:18910/ctrl"
    assert info.model_id == 20025
    assert info.serial == "SERIAL123"
    assert info.mac == "a4:e8:8d:80:54:c8"
    assert info.model_name == "Anycubic Kobra S1"
    assert info.device_type == "fdm"
    redacted = info.as_redacted_dict()
    assert redacted["token"] == "**REDACTED**"
    assert redacted["cn"] == "**REDACTED**"
    assert redacted["modelId"] == 20025


def test_parse_discovery_optional_fields_absent() -> None:
    minimal = {k: DISCOVERY[k] for k in ("ctrlType", "token", "ctrlInfoUrl", "modelId")}
    info = parse_discovery(minimal)
    assert info.serial is None
    assert info.mac is None
    assert info.model_name is None


def test_parse_discovery_numeric_string_model_id() -> None:
    assert parse_discovery({**DISCOVERY, "modelId": "20030"}).model_id == 20030


@pytest.mark.parametrize(
    ("document", "error"),
    [
        ([1, 2], InvalidResponseError),
        ("text", InvalidResponseError),
        ({**DISCOVERY, "ctrlType": "cloud"}, LanModeDisabledError),
        ({"ctrlType": "cloud"}, LanModeDisabledError),
        ({k: v for k, v in DISCOVERY.items() if k != "token"}, UnsupportedPrinterError),
        (
            {k: v for k, v in DISCOVERY.items() if k != "ctrlInfoUrl"},
            UnsupportedPrinterError,
        ),
        (
            {k: v for k, v in DISCOVERY.items() if k != "modelId"},
            UnsupportedPrinterError,
        ),
        ({**DISCOVERY, "token": "short"}, UnsupportedPrinterError),
        ({**DISCOVERY, "modelId": True}, UnsupportedPrinterError),
        ({**DISCOVERY, "modelId": "S1"}, UnsupportedPrinterError),
        ({**DISCOVERY, "ctrlInfoUrl": ""}, UnsupportedPrinterError),
        ({**DISCOVERY, "ctrlType": "other"}, UnsupportedPrinterError),
        (
            {k: v for k, v in DISCOVERY.items() if k != "ctrlType"},
            UnsupportedPrinterError,
        ),
        ({"model": "Kobra 2", "version": "1"}, UnsupportedPrinterError),
    ],
)
def test_parse_discovery_errors(document: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_discovery(document)


@pytest.mark.parametrize(
    ("broker", "expected"),
    [
        ("mqtts://10.0.66.28:9883", ("mqtts", "10.0.66.28", 9883)),
        ("mqtts://10.0.66.28", ("mqtts", "10.0.66.28", 9883)),
        ("mqtt://printer.local:1234", ("mqtt", "printer.local", 1234)),
    ],
)
def test_parse_broker_url(broker: str, expected: tuple[str, str, int]) -> None:
    assert parse_broker_url(broker) == expected


@pytest.mark.parametrize(
    "broker", ["http://10.0.66.28:9883", "mqtts://", "mqtts://h:notaport", "nonsense"]
)
def test_parse_broker_url_errors(broker: str) -> None:
    with pytest.raises(InvalidResponseError):
        parse_broker_url(broker)


def test_parse_credentials() -> None:
    creds = parse_credentials(json.dumps(CREDENTIALS).encode())
    assert creds == BrokerCredentials(
        host="10.0.66.28",
        port=9883,
        username="printer-user",
        password="printer-pass",
        device_id="DEVICE1234",
        scheme="mqtts",
    )


@pytest.mark.parametrize(
    "plaintext",
    [
        b"\xff\xfe",
        b"not json",
        b"[1]",
        json.dumps({**CREDENTIALS, "password": ""}).encode(),
        json.dumps({k: v for k, v in CREDENTIALS.items() if k != "deviceId"}).encode(),
        json.dumps({**CREDENTIALS, "username": 5}).encode(),
        json.dumps({**CREDENTIALS, "deviceId": "a/#"}).encode(),
        json.dumps({**CREDENTIALS, "broker": "tcp://x"}).encode(),
    ],
)
def test_parse_credentials_errors(plaintext: bytes) -> None:
    with pytest.raises(InvalidResponseError):
        parse_credentials(plaintext)


def test_reprs_redact_secrets() -> None:
    info = parse_discovery(DISCOVERY)
    creds = parse_credentials(json.dumps(CREDENTIALS).encode())
    for text in (repr(info), repr(creds)):
        assert TOKEN not in text
        assert "printer-user" not in text
        assert "printer-pass" not in text
        assert "**REDACTED**" in text
    assert "DEVICE1234" in repr(creds)
    assert "20025" in repr(info)


# -- full handshake -------------------------------------------------------------


async def test_handshake_success() -> None:
    fake = session()
    result = await handshake(fake, " 10.0.66.28 ", clock=lambda: 1754640000.123)
    assert result.host == "10.0.66.28"
    assert result.model_id == 20025
    assert result.model_name == "Anycubic Kobra S1"
    assert result.model == "Kobra S1"
    assert result.serial == "SERIAL123"
    assert result.mac == "a4:e8:8d:80:54:c8"
    assert result.device_id == "DEVICE1234"
    assert result.credentials.port == 9883
    assert "printer-pass" not in repr(result)
    assert TOKEN not in repr(result)

    calls = cast("FakeSession", fake).calls
    (get_method, get_url, get_timeout), (post_method, post_url, _) = calls
    assert get_method == "GET"
    assert str(get_url) == "http://10.0.66.28:18910/info"
    assert get_timeout.total == 10.0
    assert post_method == "POST"
    query = post_url.raw_query_string
    assert list(post_url.query) == ["ts", "nonce", "sign", "did"]
    assert post_url.query["ts"] == "1754640000123"
    nonce = post_url.query["nonce"]
    assert post_url.query["sign"] == build_signature(TOKEN[:16], 1754640000123, nonce)
    assert re.fullmatch(r"[A-Z0-9]{32}", post_url.query["did"])
    assert query.startswith("ts=1754640000123&nonce=")
    assert str(post_url).startswith("http://10.0.66.28:18910/ctrl?")


async def test_model_name_fallbacks() -> None:
    no_name = {k: v for k, v in DISCOVERY.items() if k != "modelName"}
    result = await handshake(session(get=no_name), "h")
    assert result.model_name == "Anycubic Kobra S1"
    unknown = {**no_name, "modelId": 12345}
    result = await handshake(session(get=unknown), "h")
    assert result.model_name == "Anycubic printer (model 12345)"
    assert result.model == "Anycubic printer (model 12345)"


async def test_fetch_discovery_non_json_content_type_tolerated() -> None:
    # The body is JSON but nothing claims so; the fake sends no content type.
    info = await fetch_discovery(session(), "10.0.66.28")
    assert isinstance(info, DiscoveryInfo)


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        aiohttp.ClientConnectionError("refused"),
        OSError("no route"),
    ],
)
async def test_discovery_unreachable(error: Exception) -> None:
    with pytest.raises(PrinterUnreachableError):
        await handshake(session(get=error), "10.0.66.99")


async def test_discovery_invalid_host() -> None:
    with pytest.raises(PrinterUnreachableError):
        await handshake(session(), "bad host/with path")


async def test_discovery_http_client_error() -> None:
    with pytest.raises(InvalidResponseError):
        await handshake(session(get=aiohttp.ClientPayloadError("broken")), "h")


async def test_discovery_http_status() -> None:
    with pytest.raises(InvalidResponseError):
        await handshake(session(get=FakeResponse(404, b"{}")), "h")


@pytest.mark.parametrize("body", [b"<html>", b"[1,2]", b'"text"'])
async def test_discovery_bad_body(body: bytes) -> None:
    with pytest.raises(InvalidResponseError):
        await handshake(session(get=body), "h")


async def test_discovery_lan_mode_off() -> None:
    with pytest.raises(LanModeDisabledError):
        await handshake(session(get={**DISCOVERY, "ctrlType": "cloud"}), "h")


async def test_discovery_unsupported() -> None:
    with pytest.raises(UnsupportedPrinterError):
        await handshake(session(get={"deviceType": "fdm", "ctrlType": "lan"}), "h")


async def test_control_unreachable() -> None:
    with pytest.raises(PrinterUnreachableError):
        await handshake(session(post=TimeoutError()), "h")


async def test_control_rejected() -> None:
    with pytest.raises(RequestRejectedError) as err:
        await handshake(session(post={"code": 403, "message": "bad sign"}), "h")
    assert err.value.code == 403
    assert err.value.printer_message == "bad sign"


async def test_control_rejected_without_message() -> None:
    with pytest.raises(RequestRejectedError) as err:
        await handshake(session(post={"code": True}), "h")
    assert err.value.printer_message is None


@pytest.mark.parametrize(
    "document",
    [
        [1],
        {"code": 200},
        {"code": 200, "data": None},
        {"code": 200, "data": {"token": IV_SOURCE}},
        {"code": 200, "data": {"info": "x"}},
        {"code": 200, "data": {"info": 1, "token": IV_SOURCE}},
    ],
)
async def test_control_bad_response(document: Any) -> None:
    with pytest.raises(InvalidResponseError):
        await handshake(session(post=document), "h")


async def test_control_not_json() -> None:
    with pytest.raises(InvalidResponseError):
        await handshake(session(post=b"oops"), "h")


async def test_control_wrong_key() -> None:
    post = control_response(key="X" * 32)
    with pytest.raises(InvalidResponseError):
        await handshake(session(post=post), "h")


async def test_control_decrypts_non_json() -> None:
    with pytest.raises(InvalidResponseError):
        await handshake(session(post=control_response(b"plain text")), "h")


@pytest.mark.parametrize("ctrl", ["/relative/ctrl", "ftp://h/ctrl", "http://[bad/ctrl"])
async def test_control_url_invalid(ctrl: str) -> None:
    with pytest.raises(InvalidResponseError):
        await handshake(session(get={**DISCOVERY, "ctrlInfoUrl": ctrl}), "h")
