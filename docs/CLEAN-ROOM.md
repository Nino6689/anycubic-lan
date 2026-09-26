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

## Similarity checks

| Date | Artefact | Compared against | Longest identical run (non-blank, non-comment lines) | Result |
|---|---|---|---|---|
