# Clean-room record

This library and the Home Assistant core integration built on it are written
so that they contain **no code or expression** from two GPL-3.0 projects:

- `WaresWichall/hass-anycubic_cloud` (the original Anycubic Cloud integration)
- `Nino6689/hass-anycubic` and `Nino6689/anycubic-cloud-api` (its fork and
  the fork's API library)

The fork's maintainer (Nino Bondonno) has worked on those projects, so the
work is split into two teams.

## Roles

| Role | Who | May read | Must not read |
|---|---|---|---|
| **Specification team** ("dirty") | Nino Bondonno, and Claude sessions on his machine that have read the GPL projects | Everything | — |
| **Implementation team** ("clean") | A separate Claude cloud session per phase, with no access to Nino's machine | This repository's `docs/`, the `anycubic-lan` package, Python and dependency documentation, the Home Assistant developer docs and `home-assistant/core` | The three repositories above, and any other Anycubic Home Assistant integration (e.g. adamoutler, chrisfore) |

Rules:

1. The specification team writes **facts and requirements only** — protocol
   behaviour, captured payloads, entity lists — in `docs/`. It never writes or
   edits code in this repository or in the core integration.
2. The implementation team writes **all code**, from `docs/` and public
   documentation. When a fact is missing it asks in `docs/QUESTIONS.md`; it
   does not look elsewhere.
3. Feedback from hardware testing reaches the implementation team only as
   functional bug reports (observed behaviour vs expected), never as code or
   diffs.
4. Before publication, the finished code is compared mechanically against the
   GPL projects and the result recorded below.

## Log

| Date | Team | Session | Inputs given | Outputs | Did not read the excluded repos |
|---|---|---|---|---|---|
| 2026-09-26 | Specification | Claude (local, Nino's machine) | Captured payloads from Nino's Kobra S1; Kobra X logs from a user; the public `anycubic_ha_local` protocol description; notes from testing the fork | `PROTOCOL.md`, `INTEGRATION-SPEC.md`, this file, `LICENSE`, `README.md`, CI workflows | n/a — specification team |
| 2026-09-26 | Implementation | Claude cloud session (routine) | `docs/CLEAN-ROOM.md`, `docs/PROTOCOL.md`, `docs/INTEGRATION-SPEC.md`, `docs/QUESTIONS.md`, `README.md`, `LICENSE`, CI workflows; general knowledge of the Python, aiohttp, paho-mqtt, cryptography and pytest APIs and the installed packages themselves (no web searches, no Anycubic code) | `src/anycubic_lan/` (v0.1.0), `tests/`, `pyproject.toml`, `.gitignore`, README sections, questions Q1–Q9 in `QUESTIONS.md` | Yes |
| 2026-09-26 | Specification | Claude (local) | The v0.1.0 implementation (for acceptance only); the GPL projects (for the similarity check) | Answers to Q1–Q9 in `QUESTIONS.md`; `PROTOCOL.md` §6.7 corrected; similarity checks below | n/a — specification team |
| 2026-09-26 | Implementation | Claude cloud session (routine, round 2) | `docs/QUESTIONS.md` (answers to Q1–Q9), `docs/PROTOCOL.md` (incl. corrected §6.7), `docs/INTEGRATION-SPEC.md`, `docs/CLEAN-ROOM.md`, `README.md`, the CI workflow, this branch's own code and tests; the installed Python, paho-mqtt, pytest, mypy and ruff (no web searches, no Anycubic code) | `src/anycubic_lan/` and `tests/` updated for Q1–Q4 and Q9, comments for Q5–Q8; "Applied in round 2" marks in `QUESTIONS.md`; README status line; this row. Merged the concurrent commits `ce0ee48` and `ca86d53` pushed to this branch during the session, keeping this session's Q1–Q4/Q9 code where both overlapped | Yes |
| 2026-09-28 | Specification | Claude (local) | Nino's Kobra S1 in LAN Mode; the v0.1.0 branch's public API (black-box script, not committed) | Hardware report HW1–HW3 in `QUESTIONS.md`; corrections to `PROTOCOL.md` §2, §6.8, §6.9 and the Q5 answer | n/a — specification team |
| 2026-09-28 | Implementation | Claude cloud session (routine, round 3) | `docs/QUESTIONS.md` (HW1–HW3), `docs/PROTOCOL.md` (corrected §2, §6.8, §6.9), this branch's code and tests (no web searches, no Anycubic code) | Fixes for HW1–HW3 in `reports.py`, `client.py` docstring and `README.md`; tests from the live captures; "Fixed" notes in `QUESTIONS.md`; this row | Yes |
| 2026-09-28 | Specification | Claude (local) | The core branch run against the Kobra S1 in a throwaway Home Assistant; the library re-run after round 3 | HW1–HW2 confirmed fixed on hardware; HW4 reported; `PROTOCOL.md` §2 discovery fields added | n/a — specification team |
| 2026-09-28 | Implementation | Claude cloud session (core integration, round 2) | `docs/QUESTIONS.md` (HW4), `docs/PROTOCOL.md` §2 and §6.1, this library's source at `3f8ac33` (`DiscoveryInfo.as_redacted_dict`, `parse_discovery`); core's own code and dev tooling for house style (no web searches, no Anycubic code) | Core branch `anycubic-integration` `68757a01` (diagnostics redact `fileUploadurl` by key, use the library's redacted discovery copy, scrub any string containing `gcode_upload?s=`) and `cfb7317c` (discovery fixture refreshed with the live fields and a string `modelId`, regression test, snapshot); "Fixed on core branch" note under HW4; this row | Yes |
| 2026-09-28 | Specification | Claude (local) | Core branch `cfb7317` and library `5b8b406`, both run against the Kobra S1 | HW1, HW2 and HW4 confirmed fixed on hardware (HW3 settled by documentation); similarity rechecked | n/a — specification team |
| 2026-09-28 | Specification | Claude (local), at Nino's instruction | The tested core branch head `cfb7317` | Squashed to one commit `27c0daa` authored by Nino for submission (identical file tree, verified). **The seven per-commit implementation commits are preserved unchanged on branch `anycubic-integration-clean-room-history` of `Nino6689/core`.** | n/a — specification team |
| 2026-10-13 | Implementation | Claude cloud session (Beta 2, D1–D8) | This repository's `docs/CLEAN-ROOM.md`, `docs/QUESTIONS.md` (Q1, Q2), `docs/PROTOCOL.md` (§6.1, §6.2 `last_project`, §7.2) and `docs/INTEGRATION-SPEC.md` (searched), its own `src/anycubic_lan/` and `tests/`; `Nino6689/hass-anycubic-next` `docs/ACCEPTANCE.md` ('Beta 2', D1–D8) and `docs/CLEAN-ROOM.md`; `Nino6689/anycubic-cloud-client` `docs/PROTOCOL.md` (B §5.3, §5.4.3) and `src/anycubic_cloud_client/messages.py`; the installed pytest, ruff and mypy (no web searches, no Anycubic code) | Branch `clean/beta2`: a refused `multiColorBox` reply takes a fault code found in `data.code` and never changes the boxes (D2); `PrintReport.channel_no`, `PrinterState.channel_no` / `active_channel` / `with_channel` (D4); untasked `print`/`updated` reports update the running job (D5); tests, including one box request per connection (D3); this row. Version not changed | Yes |
| 2026-10-19 | Implementation | Claude cloud session (Beta 3, D9–D20) | This repository's `docs/CLEAN-ROOM.md`, `docs/PROTOCOL.md` (§6.9, §7.2 'Reports that carry more'; searched for `extfilbox` and `loaded_slot`), its own `src/anycubic_lan/` and `tests/`; `Nino6689/hass-anycubic-next` `docs/ACCEPTANCE.md` ('Beta 3', D9–D20) and `docs/CLEAN-ROOM.md`; `Nino6689/anycubic-cloud-client` `src/anycubic_cloud_client/messages.py`; the installed pytest, ruff and mypy (no web searches, no Anycubic code) | Branch `clean/beta3`: job numbers read as a number or text, negative included, and `Job.job_id` (D15); `FilamentFeed`, `FeedSource`, `filament_feed()` and `PrintReport.feed` for the filament steps, which never touch the job (D10); `current_filament()` and `ExternalFilamentBoxReport.feed`, the `auto` report no longer replacing the holder (D13); `AceDrying.humidity` and a box given as an object (D11); log lines without the printer's address or device id (D14); `tests/test_beta3.py`; this row. Version not changed | Yes |
| 2026-10-20 | Implementation | Claude cloud session (Beta 4, D21–D23) | This repository's `docs/CLEAN-ROOM.md`, `docs/PROTOCOL.md` (§6.3, §6.7; searched for `humidity`, `chamber` and `box_fan_level`), the `chamber_temperature` row of `docs/INTEGRATION-SPEC.md`, its own `src/anycubic_lan/reports.py` and `tests/`; `Nino6689/hass-anycubic-next` `docs/ACCEPTANCE.md` ('Beta 4', D21–D23), `docs/COMPAT.md` and `docs/CLEAN-ROOM.md`; `Nino6689/anycubic-cloud-client` `src/anycubic_cloud_client/models.py` and `messages.py`; the installed pytest, ruff and mypy (no web searches, no Anycubic code) | Branch `clean/beta4`: `AceBox.humidity`, an ACE's own humidity reading, kept through partial reports (D22); `tests/test_beta4.py` (D22, and the chamber reading D21 relies on); this row. Version not changed | Yes |

## Similarity checks

| Date | Artefact | Compared against | Longest identical run (non-blank, non-comment lines) | Result |
|---|---|---|---|---|
| 2026-09-26 | `src/anycubic_lan/` @ `b7c0042` | `hass-anycubic` integration, `anycubic-cloud-api` library, `WaresWichall/hass-anycubic_cloud` | 6 — alphabetised stdlib imports (`hashlib, json, re, secrets, string, time`); next 4 — the standard `ssl` no-verification idiom | Clean: both are dictated by the language, not copied expression |
| 2026-09-26 | `tests/` @ `b7c0042` | the same, plus `anycubic-cloud-api/tests` | 15 — the captured `info.project` payload | Expected: data captured from a printer, copied from `PROTOCOL.md` §6.2 |
| 2026-09-26 | `src/anycubic_lan/` @ `b87f11e` (after round 2) | same three projects | 6 — the same stdlib import block; next 4 — the same `ssl` idiom | Clean; unchanged by round 2 |
| 2026-09-28 | `src/anycubic_lan/` @ `5b8b406` (after hardware fixes) | same three projects | 6 — the same stdlib import block | Clean; unchanged by rounds 3–4 |
| 2026-09-28 | core `homeassistant/components/anycubic/` @ `cfb7317` (after HW4) | same three projects | 5 — HA's sensor import block | Clean; unchanged by the HW4 fix |
| 2026-09-28 | core `tests/components/anycubic/` @ `cfb7317` | the same, plus both GPL test suites | 2 | Clean |

