# anycubic-lan

Talk to an Anycubic 3D printer in **LAN Mode**, directly on your network: no
Anycubic account, no cloud.

A printer with LAN Mode switched on runs its own MQTT broker. This library
performs the printer's handshake to get the broker credentials, connects,
asks for state, parses the reports into typed objects, and sends the commands
the printer accepts locally. It is fully async and has no cloud code and no
bundled certificates or keys.

Tested on a Kobra S1 (firmware 2.7.2.7). Reports from a Kobra X (firmware
2.0.2.2) informed the parser.

## Install

```sh
pip install anycubic-lan
```

Python 3.13 or later. Dependencies: `aiohttp`, `paho-mqtt`, `cryptography`.

Switch LAN Mode on at the printer first: **Settings → Network → LAN Mode**.
While LAN Mode is on the printer is not connected to the Anycubic cloud.

## Usage

```python
import asyncio

import aiohttp

from anycubic_lan import AnycubicLanClient, AnycubicLanError, handshake


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        info = await handshake(session, "192.168.1.50")  # the printer's IP
    print(info.model_name, info.device_id)

    client = AnycubicLanClient(info)
    client.add_state_listener(
        lambda state: print(state.status, state.temperatures.nozzle, state.job)
    )
    # Fires on changes after connect(): False when lost, True when restored.
    client.add_connection_listener(lambda up: print("restored" if up else "lost"))

    await client.connect()  # subscribes and sends every query
    try:
        for _ in range(4):
            await asyncio.sleep(15)
            await client.query_all()  # the printer answers queries; poll them
        await client.light_on()
    except AnycubicLanError as err:
        print("printer error:", err)
    finally:
        await client.disconnect()


asyncio.run(main())
```

- `handshake()` raises `PrinterUnreachableError`, `LanModeDisabledError`,
  `UnsupportedPrinterError`, `RequestRejectedError` or `InvalidResponseError`
  (all subclasses of `AnycubicLanError`).
- `client.state` is an immutable `PrinterState` merged from every report:
  status, temperatures, fans, speed mode, firmware, the current job (progress,
  layers, times, task id), ACE boxes and slots, lights, head position,
  capability flags, camera URL and the last printer error code.
- Commands: `pause()`, `resume()`, `stop()` (for the current job),
  `light_on()`, `light_off()`, `set_light_brightness()`.
- The broker credentials rotate when the printer restarts. They are held in
  memory only; if the connection does not come back, run the handshake again.

## Supported printers

| Model | Model id | Status |
|---|---|---|
| Kobra S1 | 20025 | Tested (firmware 2.7.2.7, with ACE Pro) |
| Kobra X | 20030 | Parser informed by user logs (firmware 2.0.2.2) |

Other models that offer LAN Mode with the same handshake should work and are
reported as "Anycubic printer (model &lt;id&gt;)". Older models (Kobra 2 and
earlier) are detected and refused as unsupported.

## Status

Version 0.1.0, alpha. The specification in [`docs/`](docs/) comes first; the
implementation follows it. Questions to the specification team and their
answers are in [`docs/QUESTIONS.md`](docs/QUESTIONS.md). See
[`docs/CLEAN-ROOM.md`](docs/CLEAN-ROOM.md) for how this library was written
and by whom.

## Development

```sh
pip install -e ".[test]" ruff mypy
ruff check . && ruff format --check .
mypy --strict src
pytest
```

## Licence

MIT.
