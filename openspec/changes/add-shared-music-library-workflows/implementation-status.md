# Implementation and verification: i9

Change: `add-shared-music-library-workflows`
Checkout: `C:\Users\brise\source\repos\AlexandreBrisebois\soundtouch-service`
Base HEAD remains `3796e57`. All project changes are local, unstaged and uncommitted.

## Outcome

All 21 locally verifiable implementation tasks are complete (21/24 overall). The remaining tasks are
7.3 native hardware/library lifecycle qualification, 7.4 real folder/playlist,
physical-button and audible qualification, and 7.5 physical-phone thumb-reach review.
No real application, speaker/NAS action or production test was used as evidence.

The prior dependency blocker is resolved: the user explicitly approved a temporary
Python environment and pinned test dependencies. Requirements were inspected first:
only pinned registry packages and the local requirements.txt include were present.
Packages came from official PyPI into `%TEMP%\wisp-test-env`; no global Python or
Git configuration changed. A dedicated Linux test image was built from official
Python and Node images with the same pinned requirements. Test execution had
`--network none`, a read-only checkout and temporary writable state only.

## Delivered behavior and reuse

- Shared library catalog with per-speaker Not registered / Registered unavailable /
  Ready observations. Native speaker discovery, explicit Add/Remove, exact-account
  removal, XML validation, durable unknown intent and readback before explicit retry.
- Existing registrations are imported into the catalog. Current discovery IDs and
  visibility are separate from retained added libraries; empty discovery is honest.
- Durable direct folder/playlist schedules survive reload and browse-token expiry.
  Validation, normalization, persistence and dispatch recognize the source together;
  invalid/unsupported/conflicting collection data never becomes Button 1.
- Target access uses that speaker's native hierarchy and identity. Saved native
  identities on the pinned speaker must still match; same-name replacement fails
  closed. Immediate selection reuses the existing guarded playback engine.
- Existing six-slot readout, preview, durable assignment intent and whole-map
  readback are reused. Button replacement persists warned review pauses before
  writing; uncertainty retains them. Direct collection schedules are unaffected.
- Library removals reconcile confirmed impacts across speakers, including delayed
  propagation and unreadable observations. Temporary unavailable sources skip ON
  with reason, no fallback/catch-up or automatic pause/delete/registration. Explicit
  impact pauses survive recovery and require exact revision-reviewed re-enable.
- Phone Speakers/Music navigation, Music Radio/Music Libraries, inspect-only rows,
  retained browse pages/scroll and trial text actions above a reserved dock area.
- The existing editor retains settings through Change music, Radio replacement and
  speaker changes. Cross-speaker collection-origin edits move in one serialized
  mutation instead of leaving duplicate active routines.
- Global Radio uses transient unsaved drafts, guarded quiet Test, exact Stop and
  human audible confirmation before Save. Existing stations are not retroactively
  invalidated. Saved quiet Test supports Stop without changing its quiet intent.

## Final checks

| Check | Final result |
|---|---|
| Complete Linux isolated pytest suite | **962 passed, 1 skipped**, 7.58 seconds |
| Windows-portable aggregate | **914 passed, 1 skipped, 10 deselected**, 8.47 seconds; release-fixture module excluded on Windows and fully exercised in Linux |
| Actual pytest UI set | **81 passed** in owner verification; included in the final aggregate runs |
| Ruff `check app tests` | Passed |
| Default configured mypy | Passed: **22 source files**; six new modules added to default configuration |
| JavaScript syntax: music/stations/presets and template inline script | Passed |
| Strict OpenSpec, all specs/changes | **13 passed, 0 failed** |
| Tracked and untracked whitespace | Passed |
| Independent read-only review | Reported no remaining substantive defect in corrected paths |

The one aggregate skip is `tests/test_radio_hls.py:166`: the existing Linux FFmpeg
adapter integration fixture requires FFmpeg, absent from these test environments.
Mocked HLS/resource/lifecycle regressions still ran in Linux. This skip does not
claim codec, provider or hardware qualification.

The initial full Windows run exposed 10 pre-existing platform-specific failures
and 15 temporary Git-fixture setup errors from inherited unavailable signing
configuration. No production logic or global signing settings were weakened to
make them green. POSIX filesystem modes, signals/resource limits, tzset, socket
close behavior, platform path formatting and all release fixtures passed in the
complete Linux run. The final Windows-portable command explicitly deselected those
10 cases and ignored `tests/test_docker_release.py`; Linux covered that entire
module. No project commit was made; release tests create disposable synthetic Git
repositories inside the test environment.
A final scope check removed a confirmed test-generated default config.json and
isolated the legacy favorites fixture schedule state under tmp_path. The affected
52 Windows tests passed (one POSIX-mode case left to Linux); the full Linux suite
was rerun read-only without a runtime config in the checkout.

Final Linux invocation:

```powershell
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=512m --mount 'type=bind,source=C:\Users\brise\source\repos\AlexandreBrisebois\soundtouch-service,target=/workspace,readonly' wisp-isolated-verification:20261101 python -m pytest -q -rs -p no:cacheprovider --basetemp=/tmp/wisp-pytest
```

Windows commands use `%TEMP%\wisp-test-env\Scripts\python.exe -X utf8` for pytest,
Ruff and mypy. Strict spec validation uses the existing temporary pinned
OpenSpec1.14.3 CLI. The temporary Linux build inputs are in
`%TEMP%\wisp-linux-verification`; official Python digest:
`sha256:22caa054c0d309b1eee6f448326a8821a674a75b98653247fe706db90491fc87`.
Official Node24.11.1 image digest used by the build:
`sha256:48abc13a19400ca3985071e287bd405a1d99306770eb81d61202fb6b65cf0b57`.

## Synthetic layout evidence

Local fixtures removed all application/network scripts and external assets. Both
390x844 and 320x640 iframe surfaces passed; outer headless captures are500x1000,
so these are constrained synthetic surfaces, not actual phones. Surface document
width equals viewport width, with horizontalOverflow=false.

- 390x844: last row/Load more bottom586 <= actionsTop626;
  actionsBottom780 = dockTop780; dockBottom844.
- 320x640: bottom382 <= actionsTop422;
  actionsBottom576 = dockTop576; dockBottom640.

Screenshots and metrics are in `%TEMP%\wisp-synthetic-layout\` and
`%TEMP%\wisp-synthetic-layout-small\`. Final UI follow-ups changed source-edit and
review behavior, not these CSS dimensions. Bounded scrollable action height also
keeps long names from expanding over the final row. Physical thumb reach remains
unqualified.

## Review findings resolved

Independent review and test fixes covered:

1. Same-name content substitution: verify original native identity, including ancestors.
2. Stale reviewed edits: API and queued worker compare specific pause revision tokens.
3. Delayed removal propagation: retain pending reconciliation until absence or a new
   explicitly registered epoch; never invent a firmware propagation deadline.
4. Missing favorite records: report conservative unknown impacts without aborting
   known direct/legacy impacts. Duplicate speaker names retain all candidate IDs.
5. Atomic routine moves: original snapshot/revision, verified new target and collision
   guards; stale queued edits cannot recreate a moved origin.
6. Change music to Radio: preserve the intact draft and original source identity.
7. Check Again and explicit Add/Remove retry: consistent state/retry_allowed response,
   current discovery IDs and fresh removal review before retry:true.
8. Quiet Test Stop and unknown native starts: exact-owner fresh readback recovery,
   separate quiet/stoppable intent and normal guarded STOP; no playback retry.
9. Readable library names, impacts and confirmed slot details; consistent recovery docs.

No accepted product requirement was dropped. Conservative unknown-impact pauses,
registration propagation reconciliation and downgrade limitations are documented in
`docs/music-libraries.md`, `docs/collection-schedules.md`, `docs/radio-drafts.md`,
`docs/native-presets.md` and `docs/calm-schedule-ux.md`.

## Remaining limits and boundaries

Only real hardware/physical-phone qualification remains in the OpenSpec task list.
Native API support, real playlist compatibility, physical preset recall and audible
sound are not established by fixtures. The action area remains the accepted trial.

No live speaker/NAS discovery/playback/registration/removal, production test, real
scheduler/app startup, deployment, credential/security change, project commit/push,
spec sync or archive occurred. No replacement Bose/Marge service, cloud clone,
redirect, NAS mount or parallel playback engine was introduced. All writers are
finished; changes remain available for review in the existing checkout.
