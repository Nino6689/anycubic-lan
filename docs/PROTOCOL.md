# Anycubic LAN Mode protocol — facts

This document records **observed facts** about how an Anycubic FDM printer
behaves when LAN Mode is switched on at its panel (Settings → Network → LAN
Mode). It describes wire behaviour only. It contains no source code and is
not derived from any program's source; the payloads below were captured from
real printers.

Hardware behind these facts:

- **Kobra S1**, model id `20025`, firmware `2.7.2.7`, with one ACE Pro
  (model id `40002`).
- **Kobra X**, model id `20030`, firmware `2.0.2.2`, with one ACE (logs
  supplied by a user).

The handshake was first publicly documented by the `anycubic_ha_local`
project (github.com/chrisfore/anycubic_ha_local).

Words: "the printer" = the device; "the client" = software talking to it.
Where a behaviour is unconfirmed it says so.

---

## 1. Overview

1. The client reads a **discovery document** over plain HTTP.
2. It sends a **signed control request** and receives an **encrypted blob**.
3. Decrypting the blob yields **MQTT broker credentials**.
4. The client connects to the printer's **MQTT broker over TLS**, subscribes
   to its report topic, and **asks** for each kind of state. Locally the
   printer answers queries; it does not stream everything unprompted.
5. Commands are published on a separate topic family; the printer answers
   with a report of the same type.

When LAN Mode is on, the printer drops its cloud connection. The two modes are
exclusive.

---

## 2. Discovery document

**Request:** `GET http://<host>:18910/info` — plain HTTP, no auth. A 10-second
timeout is appropriate; a wrong address usually times out rather than
refusing.

**Response:** JSON, served **without** a JSON content type (clients that
insist on `application/json` must not). Example (Kobra S1; token replaced):

```json
{
  "ctrlType": "lan",
  "token": "0123456789abcdeffedcba9876543210",
  "ctrlInfoUrl": "http://10.0.66.28:18910/ctrl",
  "modelId": 20025,
  "cn": "SERIAL123",
  "usn": "uuid:fdm:A4-E8-8D-80-54-C8",
  "modelName": "Anycubic Kobra S1",
  "deviceType": "fdm"
}
```

Fields:

| Field | Meaning |
|---|---|
| `ctrlType` | `"lan"` when LAN Mode is on. **`"cloud"` when LAN Mode is off** — the printer answers but will not hand out credentials. Treat as "not in LAN Mode". |
| `token` | 32 characters. Used for signing and decryption (§3). Changes over time. |
| `ctrlInfoUrl` | Absolute URL of the control endpoint for step 2. Use it as given. |
| `modelId` | Model id (see §9). **Sent as a string of digits** (`"20025"`) by a Kobra S1 on firmware 2.7.2.7, observed live 2026-09-28; accept an integer too. |
| `cn` | Serial number. May be absent. |
| `usn` | A URN containing the printer's MAC, e.g. `uuid:fdm:A4-E8-8D-80-54-C8`. The MAC is the six hex pairs; normalise as needed. May be absent. |
| `modelName` | Human-readable model. May be absent. |
| `deviceType` | `"fdm"` on the tested printers. |
| `ip`, `deviceName`, `zone`, `env` | Also present on a Kobra S1 (firmware 2.7.2.7, observed 2026-09-28): the printer's address, display name, `"global"`, `"prod"`. |
| `rtspUrl` | The camera stream URL (HTTP-FLV, port 18088), same as `info.urls.rtspUrl`. |
| `fileUploadurl` | **Secret.** A signed G-code upload URL, `http://<host>:18910/gcode_upload?s=<token>`. The `s` token authorises uploading files to the printer, so treat the whole URL like a password: redact it in logs and diagnostics. Note the spelling: `fileUploadurl`, lower-case `url`. The same URL also arrives as `info.urls.fileUploadurl` (§6.1). |

**Required** for the handshake: `token`, `ctrlInfoUrl`, `modelId`. Older models
(Kobra 2 and earlier) answer on this port with a different, unsigned document
lacking these fields; treat a document missing any of them as **unsupported
printer**.

Error cases the client should distinguish:

| Observation | Meaning |
|---|---|
| Connection refused / timeout / DNS failure | Unreachable (wrong address, printer off, printer asleep) |
| JSON with `ctrlType: "cloud"` | Reachable, LAN Mode switched off |
| JSON missing a required field | Unsupported (older) printer |
| Body not JSON / not an object | Bad response |

---

## 3. Signed control request → broker credentials

### 3.1 Key material

Split the 32-character `token` into two 16-character halves:

- `token[0:16]` — the **signing key**
- `token[16:32]` — the **AES key** (16 bytes, AES-128)

### 3.2 Signature

- `ts` — current time in **milliseconds** since the Unix epoch (integer).
- `nonce` — 6 random characters from `[A-Za-z0-9]`.
- `keyed = lowercase_hex(MD5(signing_key))` — MD5 of the 16-character signing
  key's ASCII bytes, as 32 lowercase hex chars.
- `sign = lowercase_hex(MD5(keyed + str(ts) + nonce))` — plain string
  concatenation, no separators.

MD5 is the printer's choice; it is not a security boundary here (the exchange
only works for a client that can already reach the printer).

### 3.3 Request

`POST <ctrlInfoUrl>?ts=<ts>&nonce=<nonce>&sign=<sign>&did=<did>`

- No body. Parameters in the query string, in that order.
- `did` — a **client** identifier: 32 characters from `[A-Z0-9]`, random per
  handshake is accepted.

### 3.4 Response

```json
{
  "code": 200,
  "data": {
    "info": "<base64 ciphertext>",
    "token": "<IV source string>"
  }
}
```

- `code` other than `200` → rejected (a `message` field may explain).
- Missing `data`, `data.info` or `data.token` → bad response.

### 3.5 Decryption

- Cipher: **AES-128-CBC**, **PKCS#7** padding (128-bit blocks).
- Key: the ASCII bytes of `token[16:32]` from the discovery document.
- IV: the ASCII bytes of `data.token`, **truncated to 16 bytes, or
  right-padded with `0x00` to 16 bytes** if shorter.
- Ciphertext: base64-decode `data.info`.
- Plaintext: UTF-8 JSON object:

```json
{
  "broker": "mqtts://10.0.66.28:9883",
  "username": "printer-user",
  "password": "printer-pass",
  "deviceId": "DEVICE1234"
}
```

(Real values: `deviceId` is 32 lowercase hex characters on both tested
printers, e.g. `372d94454cf5d746d07a8100df8674aa`.)

- `broker` is `mqtt://` or `mqtts://` + host + optional `:port`. **Default
  port 9883** when absent. The host may differ from the address used for
  discovery; use the one given.
- All four fields are required. A wrong key yields a padding error or
  non-JSON → treat as bad response.
- **Credentials rotate.** Hold them in memory for the connection's life; do
  not persist them. Re-run the handshake to reconnect after a restart of the
  printer.

---

## 4. MQTT connection

- **Transport:** TLS to the broker from §3.5.
- **Certificate:** self-signed by the printer for an address that varies per
  unit. There is no chain to validate and no stable name. Connect with
  certificate and hostname verification **disabled** (the link is still
  encrypted and stays on the LAN).
- **Credentials:** `username` / `password` from §3.5.
- **Client id:** any unique string; e.g. `ha-` + 12 random hex characters.
- **Keepalive:** 60 s works.
- **Connect timeout:** allow ~15 s for CONNACK.
- MQTT **3.1.1** is known to work.

Topic prefix: `anycubic/anycubicCloud/v1`

| Direction | Topic |
|---|---|
| Printer → client (reports) | `anycubic/anycubicCloud/v1/printer/public/<modelId>/<deviceId>/<type>/report` and deeper; subscribe to `anycubic/anycubicCloud/v1/printer/public/<modelId>/<deviceId>/#` |
| Client → printer (queries and commands) | `anycubic/anycubicCloud/v1/web/printer/<modelId>/<deviceId>/<type>` |

`<modelId>` is the discovery document's `modelId`; `<deviceId>` is the
broker's `deviceId` from §3.5.

---

## 5. Message envelope

Every report is a JSON object:

```json
{
  "type": "info",
  "action": "report",
  "timestamp": 244516,
  "msgid": "b85ca099-9792-4e2d-83df-cdd6f1a7296d",
  "state": "done",
  "code": 200,
  "msg": "done",
  "data": { }
}
```

| Field | Notes |
|---|---|
| `type` | The report kind (§6). If absent or empty, use the last topic segment that names a kind. |
| `action` | `report`, `query`, `getInfo`, `control`, `move`, `set`, … — echoes the request's action where it answers one. |
| `state` | `done`, `failed`, or a progress word. For the `print` kind, the job state (§6.2). |
| `code` | **`200` means "processed / nothing wrong".** Any other value is the printer's own error code (e.g. filament runout on an ACE slot) and should be surfaced, not treated as a transport failure. |
| `msg` | Human text accompanying `code`. |
| `msgid` | Echo of the request's `msgid` for commands; a fresh id otherwise. |
| `timestamp` | Printer uptime-ish counter; not wall-clock. |
| `data` | The payload. May be `null` (e.g. a `move` completion). |

Messages to **ignore**:

- A bare acknowledgement `{"msgid": ""}` (no `type`).
- Any message whose `type` is present but **empty** (`""`). The Kobra X emits
  many of these (≈240 in two minutes during a print); they carry nothing
  usable.
- A message with only one key on a `response` topic.

Parsing rule learned the hard way: **one unexpected value must not discard the
whole report.** Parse each field independently and keep the rest.

---

## 6. Report kinds

### 6.1 `info` — the main state report

Captured, Kobra S1 idle:

```json
{
  "type": "info", "action": "report", "state": "done", "code": 200, "msg": "done",
  "data": {
    "printerName": "Anycubic Kobra S1",
    "model": "Anycubic Kobra S1",
    "ip": "10.0.66.28",
    "version": "2.7.2.7",
    "state": "free",
    "urls": {
      "fileUploadurl": "http://10.0.66.28:18910/gcode_upload?s=SIGNED",
      "rtspUrl": "http://10.0.66.28:18088/flv"
    },
    "temp": {
      "curr_hotbed_temp": 31, "curr_nozzle_temp": 34,
      "target_hotbed_temp": 0, "target_nozzle_temp": 0
    },
    "print_speed_mode": 2,
    "fan_speed_pct": 0,
    "aux_fan_speed_pct": 0,
    "box_fan_level": 0,
    "project": null,
    "last_project": null,
    "features": {
      "auto_leveling_support": true, "vibration_compensation_support": true,
      "flow_calibration_support": true, "drying_first_support": true,
      "camera_timelapse_support": true, "gcode_3mf_support": true,
      "delete_batch_support": true, "preheating_support": true,
      "fod_support": true, "shengwang_rtc_support": true,
      "pre_cancel_support": true, "shengwang_rdt_support": true
    }
  }
}
```

| Field | Notes |
|---|---|
| `printerName`, `model` | Display names |
| `ip` | The printer's address |
| `version` | Firmware version string |
| `state` | `free` = idle/available; `busy` = printing or otherwise occupied. Other values may appear; keep the raw string. |
| `urls.rtspUrl` | Despite the name, an **HTTP-FLV** camera stream URL on port 18088 |
| `urls.fileUploadurl` | **Secret**: the signed upload URL, same as the discovery document's `fileUploadurl` (§2). Not needed for monitoring; redact it. |
| `temp.*` | Integers, °C. `curr_*` actual, `target_*` setpoint. Some models add `curr_chamber_temp` / `target_chamber_temp`; the Kobra S1 reports `0` for chamber (it has none) — treat "absent" and "always 0 on a chamberless model" as no chamber. |
| `print_speed_mode` | Integer speed preset (1 silent, 2 standard, 3 sport observed on S1; treat unknown values as raw). |
| `fan_speed_pct`, `aux_fan_speed_pct` | 0–100 |
| `box_fan_level` | Enclosure fan level, integer |
| `features` | Capability flags; keep the last seen map when a later report omits it |
| `project` | The **current job** (§6.2) or `null` when idle |
| `last_project` | `null` until a print has completed since boot; afterwards a **nested** object describing the finished job. Its presence must not break parsing. |

Setpoints are reported even with no job, so a client should keep target
temperatures from `info` independently of any job.

### 6.2 `project` block — the job, reported inside `info`

Captured mid-print, Kobra S1:

```json
{
  "remain_time": 42, "curr_layer": 3, "total_layers": 5,
  "supplies_usage": 120, "print_time": 7, "progress": 60,
  "state": "printing", "print_status": 1,
  "filename": ".3mf_temp/0622-1002-Spectacular Wolt (1)_plate(01)_PLA_0.2_45s.gcode",
  "pause": 0, "project_type": 1,
  "task_id": 614707220,
  "localtask": "b92a60d8-44d0-4b2a-916f-e5f476a07143",
  "task_settings": {"camera_timelapse": 0},
  "print_speed_mode": null
}
```

| Field | Notes |
|---|---|
| `task_id` | Integer. **Required by pause/resume/stop** (§7.2). Identifies the job; a different id means a new job. |
| `filename` | Path; the job name is the file name without directories and extension. |
| `progress` | 0–100 |
| `curr_layer`, `total_layers` | Integers |
| `print_time` | Minutes elapsed |
| `remain_time` | Minutes remaining |
| `supplies_usage` | Filament used so far (grams on the S1) |
| `pause` | `0`/`1` |
| `state` | Text: `printing`, `auto_leveling`, `paused`, `finished`, … |
| `print_status` | Integer, see below |

`print_status` values:

| Value | Meaning |
|---|---|
| 1 | Printing |
| 2 | Complete |
| 3 | Cancelled |
| 4 | Downloading |
| 5 | Checking |
| 6 | Preheating |
| 7 | Slicing |
| 8 | (never observed) |
| 9 | Levelling |
| **0** | **Sent by the Kobra X mid-print.** Not a status: keep the previous status and apply the rest of the block. |

Any other or non-numeric value: same rule — keep the previous status.

When the printer goes idle, `project` becomes `null`: clear the job so a
finished print does not look live.

### 6.3 `tempature` — temperatures (sic: the firmware's spelling)

The spelling `tempature` is what the printer uses; `temperature` gets no
reply. Captured:

```json
{
  "type": "tempature", "action": "query", "state": "done",
  "data": {
    "curr_hotbed_temp": 31, "curr_nozzle_temp": 34, "curr_chamber_temp": 0,
    "target_hotbed_temp": 0, "target_nozzle_temp": 0, "target_chamber_temp": 0
  }
}
```

### 6.4 `fan`

```json
{
  "type": "fan", "action": "query", "state": "done",
  "data": {"aux_fan_speed_pct": 0, "box_fan_level": 0, "fan_speed_pct": 55}
}
```

Any of the three may be missing; missing ≠ zero.

### 6.5 `light`

Two shapes:

- Answer to `query`: `data.lights` is a **list** of `{type, status, brightness}`.
- Answer to `control` (and pushed changes): `data` is a **single**
  `{type, status, brightness}`.

`status` 1 = on, 0 = off; `brightness` 0–100. On a Kobra S1 the controllable
light is **`type: 2`**.

### 6.6 `axis` — head position

- Answer to `query` with `state: done`:
  `data: {"coordinates": {"x": 47, "y": 276, "z": 3.8152532726237904}}` (mm).
  **The Kobra X sometimes answers with no `coordinates` at all during a
  print** — keep the last known position.
- `action: move` with `state: done` and `data: null` signals the end of a jog
  or homing move. It carries no position.

### 6.7 `multiColorBox` — ACE filament hub

Queried with action **`getInfo`** (it stays silent for `query`); the reply's
`state` is **`success`**, not `done`. The boxes are the list under
**`data.multi_color_box`** (see `QUESTIONS.md` Q1 for every action); each box:

```json
{
  "id": 0, "status": 1, "model_id": 40002, "auto_feed": 0,
  "loaded_slot": -1, "temp": 25,
  "drying_status": {"status": 0, "target_temp": 0, "duration": 0, "remain_time": 0},
  "slots": [
    {"index": 0, "sku": "", "type": "PLA", "color": [255, 255, 255],
     "status": 5, "edit_status": 0}
  ]
}
```

| Field | Notes |
|---|---|
| `id` | Box index, 0-based. Several boxes may be reported (two ACE units observed; a Kobra X can chain up to four). |
| `model_id` | `40001` = ACE Pro (Nino's Kobra S1, observed live 2026-09-28). `40002` = a different ACE unit, reported by a Kobra S1 owner (name to be confirmed, hass-anycubic #41). Treat unknown ids as a generic ACE. |
| `temp` | Box temperature °C |
| `loaded_slot` | Slot index feeding the printer; **`-1` = none reported**. On the S1 it can read `-1` while a slot's own `status` is `5`; then the slot with status 5 is the loaded one. On the Kobra X users report it freezes after many swaps (the vendor's own slicer shows the same) — treat as best-effort. |
| `auto_feed` | Runout refill, 0/1 |
| `drying_status` | `status` non-zero while drying; `target_temp` °C; `duration` and `remain_time` minutes |
| `slots[]` | `index` 0-based; `type` material; `color` RGB triple; `sku`; `status` (5 = loaded; others are presence states); `edit_status` 0 = read from an RFID tag, 1 = entered by hand, 2 = slot empty |

Fields that read `0` on this hardware and carry no information: box
`humidity`, `signal_strength`, `estimate`.

### 6.8 `aiSettings`

The settings are **nested under `data.ai_settings`**, not directly in `data`.
Captured live, Kobra S1, 2026-09-28:

```json
{"type": "aiSettings", "action": "query", "state": "done", "code": 200, "msg": "done",
 "data": {"ai_settings": {"status": 0, "type": 2, "count": 60,
                          "notice_type": [0, 1], "sensitivity_level": [1, 1]}}}
```

(AI failure detection settings; local reporting only. Changing them is
cloud-only.)

### 6.9 `peripherie`, `extfilbox`, `print`

- `peripherie` (sic) — which peripherals are fitted. Keys are **`camera`,
  `multiColorBox` (the ACE) and `udisk` (USB stick)**, each `1` fitted / `0`
  not. Ask for it: it is how a client knows a camera exists. Captured live,
  Kobra S1, 2026-09-28:
  `{"type": "peripherie", "action": "query", "state": "done", "code": 200, "data": {"camera": 1, "multiColorBox": 1, "udisk": 1}}`
- `extfilbox` — external filament holder; printers without one stay silent.
- `print` — answers only while a job exists; silent when idle. The job is
  also inside `info.project`, which is the more reliable source.

---

## 7. Queries and commands

### 7.1 Queries

Publish to `…/web/printer/<modelId>/<deviceId>/<type>`:

```json
{"type": "<type>", "action": "<action>", "data": {}}
```

| `type` | `action` |
|---|---|
| `info` | `query` |
| `tempature` | `query` |
| `fan` | `query` |
| `light` | `query` |
| `multiColorBox` | **`getInfo`** |
| `print` | `query` |
| `aiSettings` | `query` |
| `peripherie` | `query` |
| `axis` | `query` |
| `extfilbox` | `query` |

Send the whole set on connect and then periodically (every 15 s works well);
the local broker does not push everything by itself. Printers ignore kinds
they do not support.

### 7.2 Commands

Same topic; the envelope carries a millisecond `timestamp` and a fresh
`msgid` (echoed in the reply):

```json
{"type": "light", "action": "control", "timestamp": 1754640000000,
 "msgid": "8f1c…", "data": {"type": 2, "status": 1, "brightness": 100}}
```

| Purpose | `type` / `action` | `data` |
|---|---|---|
| Pause job | `print` / `pause` | `{"taskid": "<task_id>"}` |
| Resume job | `print` / `resume` | `{"taskid": "<task_id>"}` |
| Stop job | `print` / `stop` | `{"taskid": "<task_id>"}` |
| Light on/off | `light` / `control` | `{"type": 2, "status": 1|0, "brightness": 0–100}` |
| Set temperatures | `tempature` / `set` | target nozzle / hotbed fields as in §6.3 |
| Fan speed | `fan` / `setSpeed` | fields as in §6.4 |
| Jog axis | `axis` / `move` | axis and distance |
| Motors off | `axis` / `turnOff` | — |
| Query position | `axis` / `query` | — |
| ACE drying | `multiColorBox` / `setDry` | box id, temperature, duration |
| ACE feed | `multiColorBox` / `feedFilament` | box id, slot index |
| ACE slot info | `multiColorBox` / `setInfo` | slot material/colour |
| ACE auto-feed | `multiColorBox` / `setAutoFeed` | box id, on/off |

Pause/resume/stop and the light have been exercised on real hardware; the
exact field names inside `data` for temperature, fan, axis and ACE commands
should be confirmed against a printer before shipping them (they match the
cloud's order payloads, which are the same objects).

There is no reboot command in either transport.

---

## 8. Network discovery

- DHCP: MAC OUI **`A4:E8:8D`**; hostnames starting **`anycubic`** or
  **`kobra`**.
- The discovery document (§2) on port 18910 confirms it is an Anycubic
  printer and whether LAN Mode is on.

## 9. Model ids

| `modelId` | Model |
|---|---|
| 20025 | Kobra S1 |
| 20030 | Kobra X |

Others exist; report unknown ids as "Anycubic printer (model <id>)".

## 10. Behaviour when the printer goes away

- Switched off or asleep: port 18910 and the broker stop answering; ICMP ping
  may still be answered by the network module. The MQTT connection drops.
- On reconnect the old credentials may no longer work: run the full handshake
  again.
- A client should mark state unavailable **once** when the connection is lost
  and stay unavailable until the printer answers again — not flip back to the
  last known values between retries.
