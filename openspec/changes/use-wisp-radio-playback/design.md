# Design

## Context

See `proposal.md` for motivation. The current station page already supports explicit Play, Schedule, Remove, and direct diagnostic actions. Manual and scheduled station starts enter the normal playback operation model, choose native `/select` when `LOCAL_INTERNET_RADIO` is ready, and otherwise prepare a per-speaker gated relay lease. Separately, the preset panel and station menu still create radio-flavored `/storePreset` plans.

The existing relay provides the safety boundary for speakers without a native radio source: a unique speaker-bound token, upstream validation, no audio before confirmed volume zero, ownership-aware cancellation, and isolated cleanup. The direct AVTransport diagnostic cannot replace that path because URI selection may start at remembered volume.

## Goals / Non-Goals

**Goals:**

- Make station Play and station-backed schedules the only new radio selection workflows.
- Remove radio inputs from physical-preset planning without disturbing NAS preset behavior.
- Make station schedules exclusive and canonical at the API boundary.
- Preserve existing speaker maps, legacy records, descriptors needed by existing presets, and loaded schedule compatibility.

**Non-Goals:**

- No gabbo/WebSocket listener, marker preset, button interception, or physical-radio bridge.
- No source registration, firmware modification, account migration, DNS change, or automatic preset rewrite.
- No promotion of the direct ten-second diagnostic into ordinary Play or scheduled execution.
- No deletion or forced conversion of existing radio favorites or favorite-backed schedules.

## Decisions

### Keep the current radio playback orchestrator

Station Play continues through the station play endpoint and station-backed schedules continue through the scheduler's `station_id` path. Readiness remains responsible for choosing native `/select` when safe and the guarded relay otherwise. This preserves the proven ownership and volume gates and avoids creating a second radio execution engine.

An alternative was to make all radio use direct AVTransport. That was rejected because direct selection can start at remembered volume and the current contract intentionally limits it to a supervised diagnostic.

### Reject radio before constructing a physical-preset plan

The preset-plan API will accept only an opaque item token produced by a fresh browse of a READY `STORED_MUSIC` source. `station_id`, `radio_url`, and any non-NAS item are rejected before radio-base lookup, durable favorite intent, operation cancellation, or speaker access beyond the identity/read context needed by the endpoint.

The preset UI will remove its Internet radio form, and station actions will remove Assign to speaker button. NAS browsing, slot preview, whole-map concurrency check, explicit confirmation, write-ahead intent, readback, and quiet test stay unchanged.

Keeping radio assignment hidden only in the UI was rejected because old or custom clients could still overwrite a physical slot.

### Preserve legacy radio data and descriptor routes

No storage migration runs. Existing `kind=radio` favorite records remain readable, and descriptor URLs remain served because an already-programmed speaker may refetch them. Existing speaker slots are never cleared or rewritten. Existing favorite-backed schedules retain their current runtime compatibility, but the UI and API do not create new radio favorites.

Deleting descriptor support was rejected because it would silently break an existing physical preset even though this change is intended only to stop new assignments.

### Canonicalize station schedules as an exclusive playback kind

Before applying defaults, schedule validation will determine whether the request explicitly selected a station, favorite, numeric preset, or AUX. More than one kind is an error. A station choice resolves and pins the speaker, validates radio readiness when enabled, and persists `station_id` plus `speaker_id` with no `favorite_id`, `preset`, or `source`.

The browser already submits only the visible playback kind; focused tests will keep that contract and verify hidden preset fields do not leak into a station request. Older edits that omit an existing pinned identifier retain the existing compatibility rule so this change does not silently unbind saved routines.

### Keep safety and evidence claims unchanged

The change removes paths; it does not relax idle checks, volume-zero gating, fade guards, operation ownership, cancellation, source identity, speaker pinning, relay peer binding, consumer limits, or cleanup rules. Offline tests can prove the absent UI action, early API rejection, canonical schedule payload, and lack of preset writes. They cannot prove audible playback or long-running hardware compatibility.

## Risks / Trade-offs

- [Existing radio favorites remain visible in stored data and may be confusing] → Label them as legacy where surfaced and do not offer creation, reassignment, or automatic migration.
- [A custom client depends on radio preset plans] → Return a clear validation error; retain descriptor reads and existing records so removal of the write path does not break current slots.
- [Schedule normalization could accidentally default a station to preset 1] → Resolve playback kind before defaults and assert stored station schedules have null/absent favorite, preset, and source fields.
- [Removing UI controls could unintentionally affect NAS presets] → Keep NAS browse/plan/confirm tests and add negative radio cases rather than refactoring the shared confirmation machinery broadly.
- [Relay availability is mistaken for hardware qualification] → Preserve separate operation outcomes and documentation that accepted/reported playback is not audible verification.

## Migration Plan

1. Add failing API and browser tests for radio-plan rejection, absent Assign controls, and exclusive station schedules.
2. Remove the radio preset form and station assignment action while leaving station Play and Schedule intact.
3. Reject radio physical-preset inputs before any side effect and preserve NAS plan behavior.
4. Tighten schedule-kind validation and canonical storage without rewriting loaded configuration.
5. Update user documentation to describe Wisp Play/schedules as the radio path and native presets as NAS-only for new assignments.
6. Run focused tests and the complete suite, then validate OpenSpec strictly. Real-speaker radio and relay qualification remains separate and explicitly supervised.

Rollback restores the UI/API creation path only; it does not need a data rollback because this change performs no migration or speaker write.
