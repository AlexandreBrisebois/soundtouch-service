# Tasks

Local implementation was explicitly approved and verified. Real hardware, audible and physical-phone qualification remain separately authorized future work.

## 1. Native library discovery and observation

- [x] 1.1 Extend existing library transport/parser for speaker `/listMediaServers`, supported-URL checks and stable-ID deduplication with speaker visibility; verify lifecycle Discover scenarios in `tests/test_library.py` and API fixtures, including empty versus failure, duplicate names, malformed XML and no scanner/registration writes.
- [x] 1.2 Add shared library records with per-speaker Not registered / Registered unavailable / Ready observations and atomic additive persistence; verify restart, old-store preservation, offline/stale observations and explicit startup/Check Again recovery with network-disabled persistence tests; document observation states in `docs/native-presets.md`.

## 2. Explicit native Add and Remove

- [x] 2.1 Add explicit native registration with exact STORED_MUSIC XML, UUID normalization once, empty password, response validation and Adding / Checking availability / Ready outcomes; verify lifecycle Add scenarios with fixtures for HTTP-success XML error, unsupported endpoint, registered-unavailable, selection retention and no playback/preset side effects; document Add troubleshooting.
- [x] 2.2 Add pending/unknown mutation reconciliation and all-known-speaker rereads; verify lost acknowledgement, successful readback, unreadable readback, conclusive non-execution, restart and independent/propagated sources with fake transport, proving no blind retry or automatic propagation/re-add.
- [x] 2.3 Implement secondary Remove review using exact registered account and known schedule/button impacts, propagation/unknown-impact warnings and explicit confirmation; verify cancel, partial/last registration removal, unknown outcomes and no file deletion/button writes in API/store fixtures; document Remove and Add Again recovery.
- [x] 2.4 Reconcile confirmed removal impacts into durable reasoned schedule pauses and pending checks for unreadable speakers; verify settings retention, Replace music recovery and no automatic re-enable on later Ready, covering lifecycle Remove/Recover and scheduling explicit-impact scenarios.

## 3. Collection browsing and deliberate immediate playback

- [x] 3.1 Extend existing native content/API representation for folder/playlist types, independent inspect/play/preset capabilities and target-specific resolution; verify genuine playlist-shaped fixtures, unsupported assignment, Preview unavailable versus Empty, malformed identity and cross-speaker token rejection in `tests/test_library.py` and `tests/test_favorites.py` without claiming hardware qualification.
- [x] 3.2 Preserve loaded pages, scroll and path/name across Back, Load more, Retry and canceled actions; verify row taps only inspect, tracks are inspect-only, no unwanted jumps and stale-result rejection using the existing preset UI harness in `tests/test_presets_ui.py`; document shared browse and playlist limits.
- [x] 3.3 Connect inspected collection Play to existing immediate NAS playback/selection and guarded operation ownership rather than a parallel engine; verify explicit replacement/volume choice, target revalidation, same-screen reported Playing and session-specific Stop, failure retention and no autoplay/assignment/automatic target switch in operation/API/UI fixtures.

## 4. Durable direct collection schedules

- [x] 4.1 Add explicit collection binding to typed schedule data, API normalization and existing persistence queue; verify exactly-one-source rules, ignored-field/preset-1 regression, malformed/unsupported versions, old-client edit preservation and old/new persistence round trips in `tests/test_routes_validation.py` and `tests/test_scheduler_jobs.py`; document additive data and downgrade restrictions.
- [x] 4.2 Add direct collection dispatch through existing guarded select path, resolving persisted native context against the pinned target; verify expired browse tokens, restart, changed buttons, different/ambiguous collection, speaker identity change, no fallback, active-speaker politeness and volume/ownership gates in playback/scheduler tests.
- [x] 4.3 Open the existing editor from collection Schedule with name/library/speaker and Change music; verify speaker-change revalidation, intact times/days/volume/fades/radio selector, replacement cancel and Save with no playback or assignment in `tests/test_playback_ui.py` and API tests; update `docs/calm-schedule-ux.md` with the source-first path.
- [x] 4.4 Record unavailable due ON as a reasoned skip without pause/delete/source/volume writes or catch-up; verify outage, recovery at next normal occurrence, DST/restart semantics and unchanged OFF contracts in scheduler/operation fixtures; document automatic recovery versus review pauses.

## 5. Safe six-button assignment

- [x] 5.1 Reuse the six-slot current/Empty readout and existing plan/confirm/readback with collection/library/speaker/slot/old-content review and explicit Assign / Replace Button N; verify expiry, concurrent-map change, collateral-map mismatch, duplicate-content guard, canceled-browser return and no automatic playback in favorites/UI tests.
- [x] 5.2 Persist warned impact pauses for both bound and legacy slot schedules before confirmed replacement; verify pause failure blocks the write, unknown assignment retains review pauses, other slots/speakers and direct collection schedules are unaffected, and Play now remains separate; document the conservative review requirement in `docs/native-presets.md`.

## 6. Phone navigation and global Radio

- [x] 6.1 Compose Speakers / Music dock and Music Radio / Music Libraries from current views; keep Refresh Speakers / Turn All Off above the Speakers dock and existing controls/status/schedules; verify discovery/schedule/status refresh does not invoke NAS discovery/browse and accepts valid 15-second snapshots in existing UI/API fixtures; update home-navigation docs.
- [x] 6.2 Implement the accepted trial current-collection-labelled text Play / Schedule / Assign area above the dock with reserved content/safe-area space; verify narrow-viewport last row/Load more access, keyboard focus, full-width inspection targets and explanation of unsupported actions with isolated layout/UI checks; label phone thumb-reach qualification pending.
- [x] 6.3 Add transient name/URL station drafts and reuse existing guarded Test/session Stop; verify no directory/search, canonical-URL-bound eligibility, user audible acknowledgement, stopped-session gate, URL edit reset, retained fields on failures and backend Save rejection before completed test in station/API/UI fixtures; document Test then Stop then Save without retroactively invalidating saved stations.
- [x] 6.4 Keep global station Play and separate Schedule connected to existing readiness/listening-volume/session ownership; verify same-screen source/room/Stop, stale Stop refusal, failure Retry/other-speaker retention and newly saved station visibility in the existing schedule selector without a NAS hop; retain relay and diagnostic regression coverage.

## 7. Integration and separately authorized qualification

- [x] 7.1 After implementation is separately authorized and completed, run the repository's network-disabled isolated suite, configured Ruff/mypy and changed JavaScript syntax checks plus `openspec validate --all --strict --no-interactive`; record exact commands/results and regressions across legacy schedules, current NAS playback, six-slot readout, home controls and radio without starting the real app or issuing device commands.
- [x] 7.2 After implementation, review source validation/dispatch, target identity, volume gates, mutation readback and durable pause/recovery interactions against all five delta specs; deliver review findings and evidence without treating planning validation as implementation acceptance.
- [ ] 7.3 Only after separate explicit hardware authorization, qualify native discovery/add/remove, timeout readback, restart/outage recovery and independent/propagated observations on approved devices; record model/firmware and observed states, with approved disposable registrations/slots and no automated production test run.
- [ ] 7.4 Only after separate explicit hardware authorization, qualify a real folder and real playlist for browse, immediate Play/Stop and direct Schedule separately, then preset-capable assignment/readback/physical recall if approved; record audible confirmation, Preview unavailable exception where relevant and unavailable occurrence behavior without fallback.
- [ ] 7.5 After implementation and separate phone review, validate real phone thumb reach, action/dock space, browser continuity, editor and radio draft flow; record actual visual evidence and any trial-layout adjustment for design review rather than claiming current visual QA.

## Acceptance traceability

| Accepted area | Capability owner and task coverage |
|---|---|
| Preserve home/status/controls/off/schedules, immediate NAS and six-slot readout; refresh boundaries (1-2,14) | web-interface-and-api; 3.3, 5.1, 6.1-6.2, 7.1 |
| Global Radio, tested draft, separate Play/Schedule, same-screen Stop (3,8) | station-library-and-radio; 6.3-6.4 |
| Shared inspection, browser continuity, above-dock trial, playlist exception (4-5,9) | nas-library-and-native-presets + web-interface-and-api; 3.1-3.3, 6.2, 7.4-7.5 |
| Durable direct schedules, intact editor, no preset fallback (6) | schedule-management-and-execution; 4.1-4.4 |
| Explicit assignment review/readback and impact pauses (7) | nas-library-and-native-presets; 5.1-5.2 |
| Native discover/add/remove, propagation observations, recovery and docs (10-13) | music-library-lifecycle + schedule-management-and-execution; 1.1-2.4, 4.4 |
| Specs now; no prototype/implementation/live tests; separate design approval (14-15) | proposal/design boundary; every checkbox remains pending in this planning turn |
