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

## Q2 — Shape of the `print` report

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §6.9 says `print` answers only while a job exists, but gives no
payload. Is its `data` the same object as `info.project`? And what does the
answer to a `pause` / `resume` / `stop` command look like (success and
failure)? **Interim choice**: `data` is parsed as a job block when it is an
object, but only `info.project` updates the merged job; the envelope's `code`
is still recorded.

## Q3 — Full list of job `state` words

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §6.2 lists `printing`, `auto_leveling`, `paused`, `finished`, "…".
Which words mean the job is over (e.g. `stopped`, `canceled`, `failed`)?
**Interim choice**: a job counts as over only when `print_status` is 2 or 3,
or `state` is `finished`; paused when `pause` is 1 or `state` is `paused`.

## Q4 — When is a non-200 `code` cleared?

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §5 says a non-200 `code` (e.g. ACE runout) should be surfaced.
Does the printer later send `code: 200` for the same report kind once the
problem is resolved, or does the error persist until something else happens?
**Interim choice**: an error is kept per report kind until a later report of
the same kind carries `code: 200`; `last_error` is the most recent open one.

## Q5 — Type of `modelId`

*Asked by the implementation team, 2026-09-26.*

Is `modelId` always a JSON integer? **Interim choice**: an integer, or a
string of digits, is accepted; anything else is "unsupported printer".

## Q6 — `ctrlType` values other than `lan` / `cloud`

*Asked by the implementation team, 2026-09-26.*

Can `ctrlType` be missing or take another value on a printer that is in LAN
Mode? **Interim choice**: only `"lan"` proceeds; `"cloud"` is "LAN Mode off";
anything else (including missing) is "unsupported printer".

## Q7 — Broker URL with `mqtt://`

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §3.5 allows `mqtt://` or `mqtts://`; §4 says the transport is TLS.
Does `mqtt://` ever mean plain TCP? **Interim choice**: TLS is always used;
the scheme is kept in `BrokerCredentials.scheme` for diagnostics.

## Q8 — MQTT QoS for queries and commands

*Asked by the implementation team, 2026-09-26.*

Which QoS does the printer expect, and which does it publish reports with?
**Interim choice**: publish with QoS 0 and subscribe with QoS 0.

## Q9 — Brightness carried by a light "off" command

*Asked by the implementation team, 2026-09-26.*

PROTOCOL.md §7.2 gives `{"type": 2, "status": 0|1, "brightness": 0–100}`.
When switching off, which `brightness` should be sent, and does the printer
remember it for the next "on"? **Interim choice**: resend the last known
brightness of that light (0 if none is known); switching on without a
brightness resends the last known one, or 100.
