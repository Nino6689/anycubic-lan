# Home Assistant core integration `anycubic` — functional specification

What the core integration must do. How it is built is up to the implementer,
following the Home Assistant developer documentation and house style. All
wire behaviour comes from `anycubic-lan` (see `PROTOCOL.md`).

## Identity

| manifest field | value |
|---|---|
| `domain` | `anycubic` |
| `name` | `Anycubic` |
| `integration_type` | `device` |
| `iot_class` | `local_push` |
| `config_flow` | `true` |
| `requirements` | `["anycubic-lan==<released version>"]` |
| `codeowners` | `["@Nino6689"]` |
| `dhcp` | `[{"macaddress": "A4E88D*"}, {"hostname": "anycubic*"}, {"hostname": "kobra*"}]` |
| `quality_scale` | `bronze` in the first PR |

## Library API the integration needs (the library must provide this)

- An async **handshake**: given an `aiohttp.ClientSession` and a host, return
  broker credentials plus printer identity (model id, model name, serial,
  MAC, device id). Distinct exceptions for: unreachable, LAN Mode off,
  unsupported printer, bad/rejected response.
- An async **client**: connect with those credentials; register a callback
  that receives parsed state updates; `query_all()`; `disconnect()`;
  `is_connected`; a connection-lost / connection-restored signal.
- A **state model**: one object per printer with typed fields for everything
  in `PROTOCOL.md` §6 (temperatures, fans, state, speed mode, firmware,
  job with progress/layers/times/task id, ACE boxes and slots, light,
  position, last error code/message, capability flags, camera URL).
- **Commands**: pause, resume, stop (using the current job's task id), light
  on/off.

## Config flow

- **user** step: one field, `host`. Run the handshake.
  - Errors: `cannot_connect` (unreachable), `not_in_lan_mode`,
    `unsupported_printer`, `unknown`.
  - `unique_id` = the printer's `deviceId` from the handshake.
    Abort `already_configured` if it exists (and update the host).
  - Entry title = model name (e.g. "Anycubic Kobra S1").
  - `data_description` text for `host` explaining where to find the IP and
    that LAN Mode must be switched on at the printer (Settings → Network →
    LAN Mode).
- **dhcp** step: from the manifest matchers. Probe the host's discovery
  document; if it is an Anycubic printer in LAN Mode, set `unique_id` and
  abort `already_configured` with the new host if known
  (`discovery-update-info`); otherwise confirm with the user
  (`discovery_confirm`). If LAN Mode is off, abort `not_in_lan_mode`.
- **reconfigure** step: change the host; must be the same printer
  (`unique_id` match) or abort `wrong_device`.
- No credentials are stored (the printer rotates them) → reauthentication is
  exempt.

## Runtime

- Setup: handshake + connect; on failure raise `ConfigEntryNotReady`. Store
  the client and coordinator in `entry.runtime_data`.
- Coordinator: push-based. Apply each state update as it arrives; send
  `query_all()` on connect and every **15 seconds**.
- Connection lost: entities become **unavailable once**, stay unavailable, log
  a single warning; on return log a single info line and re-run the handshake
  if needed. Never alternate between stale values and unavailable.
- Unload: disconnect cleanly.
- Diagnostics: the latest parsed state and the discovery document, with
  `token`, credentials, serial and MAC redacted.

## Device

One device per entry: manufacturer `Anycubic`, model from the model id
(`PROTOCOL.md` §9), name from the printer, `sw_version` = firmware,
`serial_number` = `cn`, connection = MAC, `configuration_url` optional.

## Entities — first PR: `sensor` only

All with `has_entity_name`, translated names (`entity-translations`), icons
via `icons.json`, unique id = `<deviceId>_<key>`.

| key | what | device class / unit | state class | category / default |
|---|---|---|---|---|
| `status` | printer state: `idle`, `printing`, `paused`, `busy`, `unknown` | enum | — | — |
| `nozzle_temperature` | current nozzle °C | temperature, °C | measurement | — |
| `nozzle_target_temperature` | target nozzle °C | temperature, °C | measurement | — |
| `bed_temperature` | current bed °C | temperature, °C | measurement | — |
| `bed_target_temperature` | target bed °C | temperature, °C | measurement | — |
| `chamber_temperature` | only created if the printer reports a non-zero chamber reading | temperature, °C | measurement | — |
| `fan_speed` | part fan % | %, | measurement | disabled by default |
| `auxiliary_fan_speed` | aux fan % | % | measurement | disabled by default |
| `job_progress` | % | % | measurement | — |
| `job_current_layer` | layer | — | measurement | — |
| `job_total_layers` | layers | — | — | — |
| `job_elapsed` | minutes | duration, min | — | — |
| `job_remaining` | minutes | duration, min | — | — |
| `job_end_time` | now + remaining | timestamp | — | — |
| `job_name` | file name without path/extension | — | — | — |
| `job_status` | enum from `print_status`: `printing`, `complete`, `cancelled`, `downloading`, `checking`, `preheating`, `slicing`, `levelling`; `idle` when no job | enum | — | — |
| `speed_mode` | enum: `silent`, `standard`, `sport` (raw otherwise) | enum | — | — |
| `last_error_code` | printer error code; `none` when 200 | — | — | diagnostic |

Job sensors must read `idle`/unknown sensibly when there is no job — never
`unavailable` while the printer is connected.

## Later PRs (one each, after the first merges)

1. `binary_sensor`: printing, paused, ACE drying, runout-refill.
2. `button`: pause, resume, stop (available only when applicable).
3. `light`: printer light (type 2), on/off + brightness.
4. ACE sensors: per-slot material/colour/status, loaded slot, box temperature,
   drying remaining.
5. `number` + `select`: target temperatures, speed mode.
6. `camera`: the FLV stream URL from `info.urls.rtspUrl` via ffmpeg.
7. `update`: firmware version (read-only unless a local update path exists).

## Non-goals

Anycubic cloud accounts, file browsers, printing files, a custom panel or
card, filament cost ledgers, custom actions. Those belong to the separate
HACS integration.
