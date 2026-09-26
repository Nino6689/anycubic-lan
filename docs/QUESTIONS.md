# Questions from the implementation team

Append a question here when a fact you need is missing from `PROTOCOL.md` or
`INTEGRATION-SPEC.md`. Do not look for the answer elsewhere. The
specification team answers below each question.

## Q1 — Key of the box list in `multiColorBox` data

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §6.7 says `data` "contains a list of boxes" but does not name the
key. **Interim choice** (`reports.py`, `_find_boxes`): accept `data` being the
list itself, or take the first value inside `data` that is a list of objects.
What is the exact key?

**Answer (specification team, 2026-09-26):** Box list key: **`data.multi_color_box`** (a list of the box objects in §6.7). Also observed on the Kobra S1:

| `action` | `state` on success | What it carries |
|---|---|---|
| `getInfo` | **`success`** (not `done`) | full `multi_color_box` list |
| `setInfo`, `refresh` | `success` | boxes with `slots` updated |
| `autoUpdateInfo` | `done` | pushed unprompted when the loaded slot changes: boxes with `id` and `loaded_slot` |
| `autoUpdateDryStatus`, `setDry` | `success` | boxes with `temp` and `drying_status` |
| `feedFilament` | `done` | boxes with `loaded_slot` and `feed_status` |

Treat `success` and `done` as equivalent "completed" states for every kind.

**Applied in round 2.**

## Q2 — Shape of the `print` report

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §6.9 says `print` answers only while a job exists, but gives no
payload. Is its `data` the same object as `info.project`? And what does the
answer to a `pause` / `resume` / `stop` command look like (success and
failure)? **Interim choice**: `data` is parsed as a job block when it is an
object, but only `info.project` updates the merged job; the envelope's `code`
is still recorded.

**Answer (specification team, 2026-09-26):** The `print` report's `data` carries the job fields (same shape as `info.project`, with `taskid` for the task id). Its `action`/`state` pairs observed:

| `action` | `state` values |
|---|---|
| `start` | `downloading`, `checking`, `preheating`, `printing`, `finished` |
| `pause` | `pausing`, `paused` |
| `resume` | `resuming`, `resumed` |
| `stop` | `stopping`, `stopped` (the firmware also spells it **`stoped`**) |

A failed command arrives with `state: failed` and a non-200 `code`. Keeping `info.project` as the authoritative job is correct (the `print` kind is silent when idle); applying `print` reports as well is welcome but optional.

**Applied in round 2.**

## Q3 — Full list of job `state` words

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §6.2 lists `printing`, `auto_leveling`, `paused`, `finished`, "…".
Which words mean the job is over (e.g. `stopped`, `canceled`, `failed`)?
**Interim choice**: a job counts as over only when `print_status` is 2 or 3,
or `state` is `finished`; paused when `pause` is 1 or `state` is `paused`.

**Answer (specification team, 2026-09-26):** Job `state` words observed: `downloading`, `checking`, `preheating`, `auto_leveling`, `printing`, `pausing`, `paused`, `resuming`, `resumed`, `stopping`, `stopped`, `stoped` (sic), `finished`, `failed`, `canceled` and `cancelled` (both spellings occur). **Over** = `finished`, `stopped`, `stoped`, `failed`, `canceled`, `cancelled`, or `print_status` 2/3. `busy`/`free` are *printer* states (§6.1), not job states.

**Applied in round 2.**

## Q4 — When is a non-200 `code` cleared?

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §5 says a non-200 `code` (e.g. ACE runout) should be surfaced.
Does the printer later send `code: 200` for the same report kind once the
problem is resolved, or does the error persist until something else happens?
**Interim choice**: an error is kept per report kind until a later report of
the same kind carries `code: 200`; `last_error` is the most recent open one.

**Answer (specification team, 2026-09-26):** Codes **`0` and `200` both mean OK**. No observation shows the printer sending an explicit "cleared" message. Your interim rule (clear on the next OK code from the same kind) is the right behaviour; also treat a non-integer or boolean `code` as absent.

**Applied in round 2.**

## Q5 — Type of `modelId`

*Asked by the implementation team, 2026-09-26.*

Is `modelId` always a JSON integer? **Interim choice**: an integer, or a
string of digits, is accepted; anything else is "unsupported printer".

**Answer (specification team, 2026-09-26):** In the discovery document `modelId` is a JSON **integer** on both tested printers (`20025`, `20030`). In topics it appears as the same digits. Accepting a digit string too is fine.

**Applied in round 2.**

## Q6 — `ctrlType` values other than `lan` / `cloud`

*Asked by the implementation team, 2026-09-26.*

Can `ctrlType` be missing or take another value on a printer that is in LAN
Mode? **Interim choice**: only `"lan"` proceeds; `"cloud"` is "LAN Mode off";
anything else (including missing) is "unsupported printer".

**Answer (specification team, 2026-09-26):** Only `"lan"` and `"cloud"` have been observed. Your interim choice stands.

**Applied in round 2.**

## Q7 — Broker URL with `mqtt://`

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §3.5 allows `mqtt://` or `mqtts://`; §4 says the transport is TLS.
Does `mqtt://` ever mean plain TCP? **Interim choice**: TLS is always used;
the scheme is kept in `BrokerCredentials.scheme` for diagnostics.

**Answer (specification team, 2026-09-26):** Only `mqtts://` has been observed, always with TLS on port 9883. Always using TLS is correct.

**Applied in round 2.**

## Q8 — MQTT QoS for queries and commands

*Asked by the implementation team, 2026-09-26.*

Which QoS does the printer expect, and which does it publish reports with?
**Interim choice**: publish with QoS 0 and subscribe with QoS 0.

**Answer (specification team, 2026-09-26):** QoS **0** for both publishing and subscribing is what has been used against real hardware and works. Keep it.

**Applied in round 2.**

## Q9 — Brightness carried by a light "off" command

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §7.2 gives `{"type": 2, "status": 0|1, "brightness": 0–100}`.
When switching off, which `brightness` should be sent, and does the printer
remember it for the next "on"? **Interim choice**: resend the last known
brightness of that light (0 if none is known); switching on without a
brightness resends the last known one, or 100.

**Answer (specification team, 2026-09-26):** Switching **off** sends `{"type": 2, "status": 0, "brightness": 0}` — brightness **0** — and this has driven real hardware. Switching on sends `status: 1` with the requested brightness, or **100** when none is given. Do not rely on the printer remembering a previous brightness.

**Applied in round 2.**
