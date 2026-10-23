# Design

## Context

See proposal.md for motivation. A relay consumer cleanup currently closes and removes its lease before notifying playback that the owner ended. `playback.relay_ended` then changes the current operation from terminal Playing to terminal unknown. The closed lease cannot be reused, and session-bound Stop correctly refuses once no live lease owns the speaker.

The current operation registry already serializes logical ownership per speaker/device, the scheduler queue lock orders Play and Stop requests, and relay start already provides peer-bound tokens, an audio gate, fresh identity/content/volume guards, and bounded workers. Recovery must extend those seams without turning a destroyed lease or stale `PLAY_STATE` into ownership proof.

The official SoundTouch Web API reference documents STOP as distinct from POWER, source/content/play-status observation, actual and target volume, and change notifications. It does not document AVTransport URI selection, UPNP/`INVALID_SOURCE` semantics, lost-stream reconnection, or audible liveness. Those behaviors remain implementation and supervised-hardware evidence, not source-backed guarantees.

## Goals / Non-Goals

**Goals:**

- Continue one exact Wisp-owned manual or scheduled relay operation through one safely validated client-disconnect recovery.
- Preserve current ownership, peer isolation, volume-zero gating, no-retry handling, and truthful evidence boundaries.
- Let Stop/OFF, replacement, manual control, takeover, expiry, and shutdown defeat recovery deterministically.
- Keep recovery observable without exposing relay URLs, tokens, station credentials, or private content identity.

**Non-Goals:**

- No recovery for native radio, direct diagnostics, startup/gate/upstream failures, arbitrary network errors, or a second disconnect.
- No persistent recovery ledger, restart resume, new configuration, physical-preset change, station rewrite, generic SoundTouch API proxy, or broader speaker-control surface.
- No claim that reported Playing proves audible sound or that all SoundTouch firmware supports URI repush.
- No completion or archival of the two existing changes before their own task 3.3 evidence is satisfied.

## Decisions

### Preserve a recovery grant, not the closed lease

On an eligible disconnect, retain an immutable, private recovery grant on the same logical operation. It records the operation and recovery generation, pinned device ID, station ID and exact saved URL, prior relay URI, selected target volume, schedule/listening intent, one-attempt count, and monotonic expiry. The public outcome contains only safe recovery state/reason metadata.

The original relay lease is still closed immediately and its old token remains unusable. Keeping that lease reconnectable was rejected because its upstream/downstream lifetime has ended and accepting a second consumer would weaken the single-peer, single-consumer contract.

### Make recovery an explicit nonterminal phase

An eligible disconnect transitions Playing to recovery-pending rather than directly to irreversible terminal unknown. A worker reservation must succeed before the API/outcome claims recovery is in progress; worker unavailability ends unknown. The worker atomically claims the current recovery generation, performs network work outside global locks, and rechecks that generation before every reservation, write, and gate release.

Creating an unrelated child operation was rejected because the existing Play/Stop UI and schedule OFF ownership refer to the original logical operation ID. Reusing that ID while incrementing a private recovery generation preserves the user-visible session and lets stale recovery work be identified.

### Admit only the exact observed stalled state

Recovery is eligible only for `radio_client_disconnected` after the relay operation reached reported Playing. Before any write, fresh reads must confirm:

- the configured speaker still resolves to the pinned device identity;
- the operation and recovery generation remain current;
- the saved station still exists with the exact original URL;
- the speaker is ungrouped;
- source and transport identify the exact prior Wisp relay URI and UPNP content;
- actual and target volume both equal the operation's selected target; and
- the bounded recovery deadline and one-attempt budget remain available.

Any missing or mismatched evidence declines recovery. `PLAY_STATE` is necessary matching evidence for the observed stall but never sufficient proof of a live stream or audible output.

Looser matching by speaker name, source type, station ID alone, or friendly now-playing fields was rejected because it could overwrite manual or replacement content.

### Rebuild through a new gated lease

After validation, recovery prepares a new upstream and a new peer-bound relay token under the same logical owner. Preparation does not release audio. Wisp then revalidates ownership, writes volume zero, and confirms both actual and target zero before selecting the replacement URI. It waits for the pinned speaker peer to connect, confirms ownership and zero volume again, releases the gate, and requires fresh matching URI/Playing evidence before guarded fade-up to the original selected target.

Success records one recovery and returns the logical operation to reported Playing with `audible_confirmed=false`. Failure closes only the replacement resources, leaves the safest confirmed volume in place, and becomes terminal unknown. No recovery command is retried, no POWER command is used, and volume is not restored after ambiguous evidence.

Selecting the URI before zero was rejected for recovery. Although the relay gate prevents audio bytes, the observed firmware can change remembered volume during URI selection; the silent stalled source gives recovery an opportunity to confirm zero first.

### Let Stop and scheduled OFF cancel pending recovery without a stale device command

The scheduler's existing serialization boundary will reserve recovery and exact Stop/OFF work in one order. If exact session Stop or matching scheduled OFF wins while recovery is pending, it invalidates the grant and returns an explicit completed/canceled-recovery outcome without STOP or POWER, because no live relay lease remains. If recovery has succeeded, existing lease transfer and STOP-only behavior applies.

All other user controls and replacement operations cancel the grant through the existing ownership path. If a bounded device command was already reserved, it may finish, but the next generation check prevents later selection, gate release, or volume writes.

Sending STOP against the stale UPNP source was rejected because the session lease no longer owns it and the observed firmware state is not enough to authorize a device command.

### Keep protocol authority and qualification explicit

`docs/reference/README.md` will record that the Bose Web API PDF is authoritative for its documented HTTP observation/command shapes but silent on AVTransport recovery. `docs/direct-radio-tests.md` and the operation UI will continue to separate source-backed API behavior, observed firmware behavior, speaker-reported recovery, and human audible confirmation.

Implementing the complete Bose API was rejected. Wisp will continue adding typed, guarded protocol operations only when a product capability needs them; it will not expose a raw or generic control proxy that bypasses ownership and volume policy.

## Risks / Trade-offs

- [A user reproduces the same URI and volume before recovery reads it] -> Exact operation generation, station URL, identity, grouping, and short expiry reduce ambiguity; unavoidable same-state races still stop after the first detected mismatch.
- [Automatic recovery changes volume to zero during a false-positive stall] -> Require every exact fresh match and current logical ownership before the write; never recover from generic failures or stale cached/WebSocket state.
- [Firmware accepts the new URI but remains silent] -> Report protocol-level recovery only, keep audible confirmation false, and require supervised qualification.
- [Stop races an already reserved recovery write] -> Permit only that bounded command to finish and guard every subsequent action with the recovery generation.
- [A long-lived schedule disconnects repeatedly] -> Allow one recovery only; a later disconnect becomes terminal unknown rather than looping indefinitely.
- [A recovered session obscures the original incident] -> Preserve the disconnect reason, recovery attempt count, timestamps, and final recovery reason in sanitized operation metadata.

## Migration Plan

1. Add isolated failing tests for eligibility, exact evidence, one-attempt bounds, volume-zero ordering, new-token isolation, Stop/OFF races, takeover, shutdown, worker unavailability, and independent speakers.
2. Implement the volatile recovery grant, generation checks, worker reservation, guarded replacement sequence, public outcome fields, and selected-speaker messages without changing persisted data.
3. Update the focused reference and qualification documentation, then run focused tests, the complete isolated suite, Ruff, mypy, JavaScript checks, and strict OpenSpec validation.
4. Obtain independent review of ownership transfer, lock ordering, disconnect-during-Stop behavior, and every path that can select a URI or release a gate.
5. Only with explicit restart authorization, load the reviewed code. Qualify ordinary HB Play/Stop first, then one scheduled Play/OFF cycle, then one recovery case at a time. Record command acceptance, fresh source/volume readback, relay connection, and human audibility separately; keep Living Room independent.

Rollback removes the recovery path and returns eligible disconnects to the current terminal-unknown behavior. No stored data rollback is required, and rollback must not issue a speaker command.
