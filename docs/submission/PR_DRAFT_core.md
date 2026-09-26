<!--
  DRAFT — written by the implementation (clean-room) session for Nino to
  review and REWRITE IN HIS OWN WORDS before submitting. Home Assistant's AI
  policy requires the submitter to understand and be able to explain every
  change. Do not paste this as-is. Checkboxes below are ticked only where the
  implementation session could verify the item itself; the rest are for Nino.

  Branch: Nino6689/core @ anycubic-integration
-->

<!--
  You are amazing! Thanks for contributing to our project!
  Please, DO NOT DELETE ANY TEXT from this template! (unless instructed).
-->
## Breaking change
<!--
  If your PR contains a breaking change for existing users, it is important
  to tell them what breaks, how to make it work again and why we did this.
  This piece of text is published with the release notes, so it helps if you
  write it towards our users, not us.
  Note: Remove this section if this PR is NOT a breaking change.
-->


## Proposed change
<!--
  Describe the big picture of your changes here to communicate to the
  maintainers why we should accept this pull request. If it fixes a bug
  or resolves a feature request, be sure to link to that issue in the
  additional information section.
-->

DRAFT. Adds a new integration, `anycubic`, for Anycubic FDM 3D printers with
**LAN Mode** switched on (Kobra S1 tested; Kobra X from logs). It is fully
local: the printer hands out MQTT broker credentials through a signed local
handshake, and the integration connects to the printer's own broker. No
Anycubic account or cloud is involved.

Protocol handling lives in the MIT-licensed library
[`anycubic-lan`](https://github.com/Nino6689/anycubic-lan) (0.1.0). The
integration is a thin wrapper.

This first PR is limited to one platform, per the new-integration guidelines:

- Config flow: user step (host), DHCP discovery (MAC OUI `A4E88D`, hostnames
  `anycubic*` / `kobra*`) with a confirm step and host update for known
  printers, and a reconfigure step that aborts with `wrong_device` if another
  printer answers. The unique id is the printer's broker `deviceId`.
- Coordinator (`local_push`): state updates are pushed by the library's
  listener. Because the printer only answers some report kinds on request,
  all kinds are queried every 15 seconds on a fixed timer (the coordinator's
  own interval would be reset by each push and never fire during a print).
  On connection loss the entities become unavailable once, with one warning;
  they come back, with one info line, when the printer sends its state again.
  While disconnected, the handshake is re-run on each 15-second tick, because
  the printer rotates its broker credentials when it restarts.
- `sensor` platform: status, nozzle/bed (target) temperatures, chamber
  temperature (only added once a non-zero reading is seen), fan speeds
  (disabled by default), job progress/layers/elapsed/remaining/end time/name/
  status, speed mode and last error code (diagnostic).
- Diagnostics with the discovery token, serial, MAC and signed upload URL
  redacted.

Later PRs (one each): binary sensors, pause/resume/stop buttons, light, ACE
filament hub sensors, number/select, camera, update.

Quality scale: **Bronze**. All Bronze rules are done or exempt; several
Silver/Gold rules are also met (see `quality_scale.yaml`). Reauthentication is
exempt: no credentials are stored, the printer issues fresh ones at every
handshake. The mypy strict-typing list includes the integration.

## Type of change
<!--
  What type of change does your PR introduce to Home Assistant?
  NOTE: Please, check only 1! box!
  If your PR requires multiple boxes to be checked, you'll most likely need to
  split it into multiple PRs. This makes things easier and faster to code review.
-->

- [ ] Dependency upgrade
- [ ] Bugfix (non-breaking change which fixes an issue)
- [x] New integration (thank you!)
- [ ] New feature (which adds functionality to an existing integration)
- [ ] Deprecation (breaking change to happen in the future)
- [ ] Breaking change (fix/feature causing existing functionality to break)
- [ ] Code quality improvements to existing code or addition of tests

## Additional information
<!--
  Details are important, and help maintainers processing your PR.
  Please be sure to fill out additional details, if applicable.
-->

- This PR fixes or closes issue: fixes #
- This PR is related to issue: 
- Link to documentation pull request: TODO (draft page: `docs/submission/anycubic.markdown` in anycubic-lan)
- Link to developer documentation pull request: 
- Link to frontend pull request: 

## Checklist
<!--
  Put an `x` in the boxes that apply. You can also fill these out after
  creating the PR. If you're unsure about any of them, don't hesitate to ask.
  We're here to help! This is simply a reminder of what we are going to look
  for before merging your code.

  AI tools are welcome, but contributors are responsible for *fully*
  understanding the code before submitting a PR. Please follow our AI policy:
  https://developers.home-assistant.io/docs/ai_policy
-->

- [ ] I understand the code I am submitting and can explain how it works.
- [ ] The code change is tested and works locally.
- [x] Local tests pass. **Your PR cannot be merged unless tests pass**
- [x] There is no commented out code in this PR.
- [ ] I have followed the [development checklist][dev-checklist]
- [ ] I have followed the [perfect PR recommendations][perfect-pr]
- [x] The code has been formatted using Ruff (`ruff format homeassistant tests`)
- [x] Tests have been added to verify that the new code works.
- [ ] Any generated code has been carefully reviewed for correctness and compliance with project standards.

If user exposed functionality or configuration variables are added/changed:

- [ ] Documentation added/updated for [www.home-assistant.io][docs-repository]

If the code communicates with devices, web services, or third-party tools:

- [x] The [manifest file][manifest-docs] has all fields filled out correctly.  
      Updated and included derived files by running: `python3 -m script.hassfest`.
- [x] New or updated dependencies have been added to `requirements_all.txt`.  
      Updated by running `python3 -m script.gen_requirements_all`.
- [ ] For the updated dependencies a diff between library versions and ideally a link to the changelog/release notes is added to the PR description.

<!--
  This project is very active and we have a high turnover of pull requests.

  Unfortunately, the number of incoming pull requests is higher than what our
  reviewers can review and merge so there is a long backlog of pull requests
  waiting for review. You can help here!
  
  By reviewing another pull request, you will help raise the code quality of
  that pull request and the final review will be faster. This way the general
  pace of pull request reviews will go up and your wait time will go down.
  
  When picking a pull request to review, try to choose one that hasn't yet
  been reviewed.

  Thanks for helping out!
-->

To help with the load of incoming pull requests:

- [ ] I have reviewed two other [open pull requests][prs] in this repository.

[prs]: https://github.com/home-assistant/core/pulls?q=is%3Aopen+is%3Apr+-author%3A%40me+-draft%3Atrue+-label%3Awaiting-for-upstream+sort%3Acreated-desc+review%3Anone+-status%3Afailure

<!--
  Thank you for contributing <3

  Below, some useful links you could explore:
-->
[dev-checklist]: https://developers.home-assistant.io/docs/development_checklist/
[manifest-docs]: https://developers.home-assistant.io/docs/creating_integration_manifest/
[quality-scale]: https://developers.home-assistant.io/docs/integration_quality_scale_index/
[docs-repository]: https://github.com/home-assistant/home-assistant.io
[perfect-pr]: https://developers.home-assistant.io/docs/review-process/#creating-the-perfect-pr

---

## Notes for Nino (delete before submitting)

Why boxes are unticked:

- *Understand the code / generated code reviewed*: yours to confirm.
- *Tested and works locally*: only unit tests ran; nobody has run this against
  a real printer yet. Please test on the Kobra S1 (setup, a print, printer off
  and on again, DHCP rediscovery) before ticking.
- *Development checklist / perfect PR*: yours to judge.
- *Documentation*: the page is drafted but no home-assistant.io PR exists.
- *Dependency diff*: not applicable to a new dependency (there is no previous
  version to diff against); say so in your own words.

Must happen before submitting:

1. Publish `anycubic-lan==0.1.0` to PyPI (the manifest pins it; CI will fail
   without it). Tag and publish from CI so `dependency-transparency` holds.
2. Submit brand images for `anycubic` to home-assistant/brands.
3. Open the home-assistant.io docs PR (from the draft page) and link it above.
4. `quality_scale.yaml` marks `brands`, `dependency-transparency` and three
   `docs-*` rules as done with a "PENDING before submission" comment, because
   hassfest refuses a Bronze manifest with Bronze rules left `todo`. Remove
   those comments once 1–3 are done.
