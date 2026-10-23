# Tasks

## 1. Recovery ownership and eligibility

- [x] 1.1 Add focused failing operation/relay tests for recovery only after a current reported-Playing `radio_client_disconnected`, one attempt per logical operation, monotonic expiry, restart loss, worker unavailability, and no recovery for startup, gate, upstream, Stop, or shutdown endings; verify they fail for the intended missing behavior before implementation.
- [x] 1.2 Implement the private in-memory recovery grant, attempt count, generation, nonterminal outcome states, bounded worker reservation, and sanitized public metadata while preserving the original operation ID; verify the focused eligibility/outcome tests pass and no relay token, URL, or private content identity reaches API output.
- [x] 1.3 Update `docs/reference/README.md` and `docs/direct-radio-tests.md` to separate official HTTP Web API surfaces from hardware-qualified AVTransport recovery, document the one-attempt/restart boundary, and verify the text makes no audible or firmware-wide guarantee and does not advertise a generic SoundTouch API proxy.

## 2. Exact guarded relay replacement

- [x] 2.1 Add focused failing tests for fresh pinned identity, current generation, unchanged station URL, exact prior UPNP relay URI, ungrouped state, expected actual/target volume, and independent speakers; verify every unavailable or mismatched field prevents volume and URI writes.
- [x] 2.2 Add focused failing tests for a new peer-bound token, volume-zero write/readback before replacement URI selection, no audio before gate release, matching peer connection, fresh replacement Playing evidence, guarded fade to the original target, and terminal unknown handling without POWER, volume restoration, or automatic retry.
- [x] 2.3 Implement the one-shot guarded recovery sequence using existing relay preparation, fresh direct snapshots, ownership checks, write serialization, and cleanup boundaries; verify the focused sequence tests pass, the old token remains revoked, and a second disconnect never schedules another attempt.

## 3. Stop, OFF, replacement, and UI races

- [x] 3.1 Add focused failing concurrency tests proving exact listening Stop and matching schedule OFF cancel pending recovery without a speaker command, while replacement Play, manual control, source takeover, expiry, and shutdown prevent every unreserved later write; include the disconnect-during-authoritative-Stop regression and verify another speaker remains untouched.
- [x] 3.2 Implement atomic recovery invalidation through the existing queue/ownership boundaries, preserving the rule that one already reserved bounded command may finish but every later write and gate release must revalidate the generation; verify the focused Stop/OFF/replacement race tests pass.
- [x] 3.3 Add operation API and offline browser tests for pending, recovering, recovered, declined, failed, worker-unavailable, and Stop-canceled messages; implement the selected-speaker presentation and verify it never claims audible recovery, hides private recovery evidence, suppresses duplicate actions, and ignores stale speaker/view responses.

## 4. Integration, review, and hardware qualification

- [x] 4.1 Run the focused recovery, relay, playback, scheduler, route, and browser tests plus the complete isolated suite, Ruff, mypy, JavaScript syntax/whitespace checks, and strict OpenSpec validation; record passed, failed, skipped, deselected, blocked, and not-run evidence separately.
- [x] 4.2 Obtain independent review of eligibility, operation/generation ownership, worker reservation, lock ordering, volume-zero-before-URI ordering, token/peer isolation, Stop/OFF races, cleanup, privacy, and all source-selection/gate-release paths; correct and rerun affected offline checks before any restart request.
- [ ] 4.3 After separate restart and real-speaker authorization, first qualify ordinary HB listening Play and session-bound Stop with command acceptance, fresh source/volume readback, Living Room independence, and human audibility recorded separately; do not mark either existing change complete from API state alone.
- [ ] 4.4 After separate authorization for the next single action, qualify one HB station schedule ON/OFF cycle with ownership, readback, audibility, and Living Room independence recorded separately.
- [ ] 4.5 After separate authorization and only with a reviewed safe way to produce or observe one eligible HB client disconnect, qualify one recovery attempt at a safe selected volume; record old-lease revocation, new token/peer connection, zero-volume gate, replacement URI/readback, Stop behavior, and human audibility separately, and leave the task pending if the disconnect cannot be safely reproduced.

## Workflow follow-up

- Reconcile the three changes' hardware evidence independently before completing or archiving any of them.
- Sync and archive this change only after every tracked task and strict validation pass; do not treat archival as authorization to publish, commit, push, merge, restart, or send another speaker command.
