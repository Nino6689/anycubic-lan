"""LAN Mode handshake: discovery document → signed request → broker credentials.

See PROTOCOL.md §2 and §3. The credentials this produces rotate; hold them in
memory for the life of one connection and never persist them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
import string
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from yarl import URL

from .exceptions import (
    InvalidResponseError,
    LanModeDisabledError,
    PrinterUnreachableError,
    RequestRejectedError,
    UnsupportedPrinterError,
)
from .models import PRINTER_MODELS, printer_model_name

if TYPE_CHECKING:
    from collections.abc import Callable

#: Port of the discovery document and control endpoint (PROTOCOL.md §2).
DISCOVERY_PORT = 18910
#: Broker port when the ``broker`` URL has none (PROTOCOL.md §3.5).
DEFAULT_BROKER_PORT = 9883
#: Timeout for each HTTP request of the handshake, in seconds.
DEFAULT_TIMEOUT = 10.0

_REDACTED = "**REDACTED**"
_TOKEN_LENGTH = 32
_NONCE_ALPHABET = string.ascii_letters + string.digits
_DID_ALPHABET = string.ascii_uppercase + string.digits
_MAC_RE = re.compile(r"([0-9A-Fa-f]{2})[-:]?" * 5 + r"([0-9A-Fa-f]{2})")
# Characters that would change the meaning of an MQTT topic.
_TOPIC_UNSAFE = frozenset("/+#\x00")


@dataclass(frozen=True, slots=True)
class DiscoveryInfo:
    """The printer's discovery document (PROTOCOL.md §2)."""

    token: str = field(repr=False)
    ctrl_info_url: str
    model_id: int
    ctrl_type: str | None = None
    serial: str | None = None
    usn: str | None = None
    model_name: str | None = None
    device_type: str | None = None
    raw: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({}), repr=False, compare=False
    )

    def __repr__(self) -> str:
        return (
            f"DiscoveryInfo(token={_REDACTED!r}, ctrl_info_url={self.ctrl_info_url!r}, "
            f"model_id={self.model_id!r}, ctrl_type={self.ctrl_type!r}, "
            f"serial={self.serial!r}, usn={self.usn!r}, "
            f"model_name={self.model_name!r}, device_type={self.device_type!r})"
        )

    @property
    def mac(self) -> str | None:
        """MAC address from ``usn``, as ``aa:bb:cc:dd:ee:ff``; ``None`` if absent."""
        return mac_from_usn(self.usn) if self.usn else None

    def as_redacted_dict(self) -> dict[str, Any]:
        """The raw document with ``token``, ``cn`` and ``usn`` redacted."""
        return {
            key: _REDACTED if key in ("token", "cn", "usn") else value
            for key, value in self.raw.items()
        }


@dataclass(frozen=True, slots=True)
class BrokerCredentials:
    """MQTT broker credentials from the control response (PROTOCOL.md §3.5)."""

    host: str
    port: int
    username: str = field(repr=False)
    password: str = field(repr=False)
    device_id: str
    scheme: str = "mqtts"

    def __repr__(self) -> str:
        return (
            f"BrokerCredentials(host={self.host!r}, port={self.port!r}, "
            f"username={_REDACTED!r}, password={_REDACTED!r}, "
            f"device_id={self.device_id!r}, scheme={self.scheme!r})"
        )


@dataclass(frozen=True, slots=True)
class PrinterConnectionInfo:
    """Everything the handshake returns: printer identity plus credentials."""

    host: str
    discovery: DiscoveryInfo
    credentials: BrokerCredentials

    @property
    def model_id(self) -> int:
        return self.discovery.model_id

    @property
    def model_name(self) -> str:
        """``modelName`` from the printer, else a name from the model id."""
        if self.discovery.model_name:
            return self.discovery.model_name
        if self.model_id in PRINTER_MODELS:
            return f"Anycubic {PRINTER_MODELS[self.model_id]}"
        return printer_model_name(self.model_id)

    @property
    def model(self) -> str:
        """Model from the model id (PROTOCOL.md §9), e.g. ``Kobra S1``."""
        return printer_model_name(self.model_id)

    @property
    def serial(self) -> str | None:
        return self.discovery.serial

    @property
    def mac(self) -> str | None:
        return self.discovery.mac

    @property
    def device_id(self) -> str:
        return self.credentials.device_id


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------


def mac_from_usn(usn: str) -> str | None:
    """Extract the MAC from a ``usn`` such as ``uuid:fdm:A4-E8-8D-80-54-C8``."""
    match = _MAC_RE.search(usn)
    if match is None:
        return None
    return ":".join(part.lower() for part in match.groups())


def parse_discovery(document: object) -> DiscoveryInfo:
    """Validate a decoded discovery document.

    Raises :class:`InvalidResponseError` if it is not an object,
    :class:`LanModeDisabledError` for ``ctrlType: "cloud"`` and
    :class:`UnsupportedPrinterError` when a required field is missing.
    """
    if not isinstance(document, Mapping):
        raise InvalidResponseError("Discovery document is not a JSON object")
    ctrl_type = document.get("ctrlType")
    if ctrl_type == "cloud":
        raise LanModeDisabledError("LAN Mode is switched off on the printer")
    token = document.get("token")
    ctrl_info_url = document.get("ctrlInfoUrl")
    model_id = document.get("modelId")
    if isinstance(model_id, str) and model_id.isdigit():
        # modelId is a JSON integer on both tested printers; a string of the
        # same digits is accepted too (Q5 in docs/QUESTIONS.md).
        model_id = int(model_id)
    if (
        not isinstance(token, str)
        or len(token) != _TOKEN_LENGTH
        or not isinstance(ctrl_info_url, str)
        or not ctrl_info_url
        or not isinstance(model_id, int)
        or isinstance(model_id, bool)
    ):
        raise UnsupportedPrinterError(
            "Discovery document lacks a usable token, ctrlInfoUrl or modelId"
        )
    if ctrl_type != "lan":
        # Only "lan" and "cloud" have been observed (Q6 in docs/QUESTIONS.md).
        # Any other (or missing) ctrlType is refused rather than guessed at.
        raise UnsupportedPrinterError(f"Unexpected ctrlType {ctrl_type!r}")

    def optional(key: str) -> str | None:
        value = document.get(key)
        return value if isinstance(value, str) and value else None

    return DiscoveryInfo(
        token=token,
        ctrl_info_url=ctrl_info_url,
        model_id=model_id,
        ctrl_type=ctrl_type,
        serial=optional("cn"),
        usn=optional("usn"),
        model_name=optional("modelName"),
        device_type=optional("deviceType"),
        raw=MappingProxyType(dict(document)),
    )


def signing_key(token: str) -> str:
    """First half of the token (PROTOCOL.md §3.1)."""
    return token[:16]


def aes_key(token: str) -> bytes:
    """Second half of the token as AES-128 key bytes (PROTOCOL.md §3.1)."""
    return token[16:32].encode("ascii")


def build_signature(key: str, ts: int, nonce: str) -> str:
    """``md5_hex(md5_hex(key) + str(ts) + nonce)`` (PROTOCOL.md §3.2)."""
    keyed = hashlib.md5(key.encode("ascii"), usedforsecurity=False).hexdigest()
    return hashlib.md5(
        (keyed + str(ts) + nonce).encode("ascii"), usedforsecurity=False
    ).hexdigest()


def build_iv(source: str) -> bytes:
    """IV from ``data.token``: truncate or ``0x00``-pad to 16 bytes (§3.5)."""
    return source.encode("utf-8")[:16].ljust(16, b"\x00")


def random_nonce() -> str:
    """6 random characters from ``[A-Za-z0-9]``."""
    return "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(6))


def random_did() -> str:
    """A 32-character client id from ``[A-Z0-9]``."""
    return "".join(secrets.choice(_DID_ALPHABET) for _ in range(32))


def control_url(token: str, ctrl_info_url: str, ts: int, nonce: str, did: str) -> str:
    """Build the signed control URL, parameters in the documented order."""
    sign = build_signature(signing_key(token), ts, nonce)
    separator = "&" if "?" in ctrl_info_url else "?"
    return f"{ctrl_info_url}{separator}ts={ts}&nonce={nonce}&sign={sign}&did={did}"


def decrypt_info(info_b64: str, iv_source: str, key: bytes) -> bytes:
    """AES-128-CBC + PKCS#7 decrypt of base64 ``info`` (PROTOCOL.md §3.5).

    Raises :class:`InvalidResponseError` on any decoding or padding failure.
    """
    try:
        ciphertext = base64.b64decode(info_b64, validate=True)
        decryptor = Cipher(
            algorithms.AES(key), modes.CBC(build_iv(iv_source))
        ).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    except (binascii.Error, ValueError) as err:
        raise InvalidResponseError("Could not decrypt the broker credentials") from err


def parse_broker_url(broker: str) -> tuple[str, str, int]:
    """Split ``mqtt[s]://host[:port]`` into scheme, host and port."""
    try:
        parts = urlsplit(broker)
        port = parts.port
    except ValueError as err:
        raise InvalidResponseError("Broker address is not a valid URL") from err
    if parts.scheme not in ("mqtt", "mqtts") or not parts.hostname:
        raise InvalidResponseError("Broker address is not an mqtt(s) URL")
    return parts.scheme, parts.hostname, port or DEFAULT_BROKER_PORT


def parse_credentials(plaintext: bytes) -> BrokerCredentials:
    """Validate the decrypted credentials object (PROTOCOL.md §3.5)."""
    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as err:
        raise InvalidResponseError("Decrypted credentials are not JSON") from err
    if not isinstance(decoded, Mapping):
        raise InvalidResponseError("Decrypted credentials are not a JSON object")
    values = {
        key: decoded.get(key) for key in ("broker", "username", "password", "deviceId")
    }
    if not all(isinstance(value, str) and value for value in values.values()):
        raise InvalidResponseError("Decrypted credentials lack a required field")
    device_id = str(values["deviceId"])
    if _TOPIC_UNSAFE & set(device_id):
        raise InvalidResponseError("deviceId contains MQTT topic characters")
    scheme, host, port = parse_broker_url(str(values["broker"]))
    return BrokerCredentials(
        host=host,
        port=port,
        username=str(values["username"]),
        password=str(values["password"]),
        device_id=device_id,
        scheme=scheme,
    )


def parse_control_response(document: object, token: str) -> BrokerCredentials:
    """Validate the control response and decrypt its credentials (§3.4, §3.5)."""
    if not isinstance(document, Mapping):
        raise InvalidResponseError("Control response is not a JSON object")
    code = document.get("code")
    if code != 200 or isinstance(code, bool):
        message = document.get("message")
        raise RequestRejectedError(
            f"Printer rejected the control request (code {code!r})",
            code=code,
            printer_message=message if isinstance(message, str) else None,
        )
    data = document.get("data")
    if not isinstance(data, Mapping):
        raise InvalidResponseError("Control response has no data")
    info, iv_source = data.get("info"), data.get("token")
    if not isinstance(info, str) or not isinstance(iv_source, str):
        raise InvalidResponseError("Control response lacks data.info or data.token")
    return parse_credentials(decrypt_info(info, iv_source, aes_key(token)))


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    url: URL,
    request_timeout: float,
) -> object:
    try:
        async with session.request(
            method, url, timeout=aiohttp.ClientTimeout(total=request_timeout)
        ) as response:
            status = response.status
            body = await response.read()
    except (TimeoutError, aiohttp.ClientConnectionError, OSError) as err:
        raise PrinterUnreachableError(f"Printer did not answer at {url.host}") from err
    except aiohttp.ClientError as err:
        raise InvalidResponseError(f"HTTP error from {url.host}: {err}") from err
    if status != 200:
        raise InvalidResponseError(f"HTTP {status} from {url.host}")
    try:
        # The printer does not send a JSON content type (PROTOCOL.md §2).
        return json.loads(body)
    except ValueError as err:
        raise InvalidResponseError("Printer response is not JSON") from err


def _discovery_url(host: str) -> URL:
    host = host.strip()
    try:
        return URL.build(scheme="http", host=host, port=DISCOVERY_PORT, path="/info")
    except (ValueError, TypeError) as err:
        raise PrinterUnreachableError(f"Invalid printer address {host!r}") from err


async def fetch_discovery(
    session: aiohttp.ClientSession,
    host: str,
    *,
    request_timeout: float = DEFAULT_TIMEOUT,
) -> DiscoveryInfo:
    """Read and validate the discovery document at ``http://<host>:18910/info``."""
    document = await _request_json(
        session, "GET", _discovery_url(host), request_timeout
    )
    return parse_discovery(document)


async def handshake(
    session: aiohttp.ClientSession,
    host: str,
    *,
    request_timeout: float = DEFAULT_TIMEOUT,
    clock: Callable[[], float] = time.time,
) -> PrinterConnectionInfo:
    """Run the full LAN Mode handshake against ``host``.

    Raises :class:`PrinterUnreachableError`, :class:`LanModeDisabledError`,
    :class:`UnsupportedPrinterError`, :class:`RequestRejectedError` or
    :class:`InvalidResponseError`.
    """
    discovery = await fetch_discovery(session, host, request_timeout=request_timeout)
    ts = int(clock() * 1000)
    url_text = control_url(
        discovery.token, discovery.ctrl_info_url, ts, random_nonce(), random_did()
    )
    try:
        url = URL(url_text, encoded=True)
    except (ValueError, TypeError) as err:
        raise InvalidResponseError("ctrlInfoUrl is not a valid URL") from err
    if not url.absolute or url.scheme not in ("http", "https"):
        raise InvalidResponseError("ctrlInfoUrl is not an absolute HTTP URL")
    document = await _request_json(session, "POST", url, request_timeout)
    credentials = parse_control_response(document, discovery.token)
    return PrinterConnectionInfo(
        host=host.strip(), discovery=discovery, credentials=credentials
    )
