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

## Similarity checks

| Date | Artefact | Compared against | Longest identical run (non-blank, non-comment lines) | Result |
|---|---|---|---|---|
| 2026-09-26 | `src/anycubic_lan/` @ `b7c0042` | `hass-anycubic` integration, `anycubic-cloud-api` library, `WaresWichall/hass-anycubic_cloud` | 6 — alphabetised stdlib imports (`hashlib, json, re, secrets, string, time`); next 4 — the standard `ssl` no-verification idiom | Clean: both are dictated by the language, not copied expression |
| 2026-09-26 | `tests/` @ `b7c0042` | the same, plus `anycubic-cloud-api/tests` | 15 — the captured `info.project` payload | Expected: data captured from a printer, copied from `PROTOCOL.md` §6.2 |
| 2026-09-26 | `src/anycubic_lan/` @ `b87f11e` (after round 2) | same three projects | 6 — the same stdlib import block; next 4 — the same `ssl` idiom | Clean; unchanged by round 2 |
