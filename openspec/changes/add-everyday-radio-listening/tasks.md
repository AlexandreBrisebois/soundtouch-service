# Tasks

## 1. Listening API and ownership

- [x] 1.1 Add fresh listening options, explicit validated volume and speaker identity to normal Play, and a separate quiet-test endpoint; verify volume propagation, invalid inputs, distinct identity failures and no diagnostic dispatch with isolated API tests.
- [x] 1.2 Implement operation-bound Stop using atomic ownership comparison and verified STOP-only native/relay execution; verify stale requests, queued replacement, source takeover, no POWER and independent speakers with isolated operation tests.
- [x] 1.3 Reject conflicting pending station requests before cancellation and reuse only equivalent station, speaker identity, volume and intent; verify cross-intent, changed-volume, identity and station conflicts plus HTTP 409 with isolated regression tests.

## 2. Everyday interface

- [x] 2.1 Add editable fresh-volume listening controls and separate Play from diagnostic confirmation; verify stale speaker reads, explicit selection on unavailable volume, no diagnostic fallback and chosen payload in offline browser tests.
- [x] 2.2 Add session-specific Stop and honest status in the selected speaker view; verify captured station/speaker/operation IDs, duplicate suppression and stale-response isolation in offline browser tests, and document the listening flow.

## 3. Integration and qualification

- [x] 3.1 Run the full isolated suite, JavaScript syntax checks, Ruff, mypy and strict OpenSpec validation; record actual results and reconcile superseded requirements without changing schedules or presets.
- [x] 3.2 Obtain independent review of volume gates and session Stop ownership before publication.
- [ ] 3.3 After separate authorization, qualify Play/Stop and independent speakers with supervised hardware and audible checks; leave this pending during offline implementation.

Offline evidence: after the pending-request review correction, the full network-disabled Linux suite passed 775 tests. The final macOS run passed 781 tests with one skipped and one socket-close assertion deselected after its isolated run produced macOS `EBADF` instead of Linux EOF. Ruff passed, mypy reported no issues in the changed source files and in the earlier 16-file configured run, station JavaScript syntax and whitespace checks passed, and strict OpenSpec validation passed all 13 items. Independent review found and verified corrections for direct-diagnostic conflict bypass, Stop worker-reservation ownership, truthful worker-unavailable status, and the relay-disconnect race during authoritative Stop readback without weakening the volume gate, STOP-only semantics or speaker isolation. The running service was not restarted to load the final race correction and no further playback, power or volume command was sent. Hardware qualification remains pending.
