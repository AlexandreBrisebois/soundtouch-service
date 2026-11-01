# Design

## Context

See `proposal.md` for motivation and scope. Windows checkout: `C:\Users\brise\source\repos\AlexandreBrisebois\soundtouch-service`, inspected at `3796e57` with a clean initial working tree. No `AGENTS.md` exists at repo root, inside the checkout, or the checked code-folder ancestors. `.agents/skills/openspec-propose/SKILL.md` and `openspec/config.yaml` govern this planning-only change; no existing changes or main specs are edited.

Observed source seams:

| Owner | Current evidence and reuse |
|---|---|
| `app/core/library.py` | Parses direct ContentItem identity, source availability, bounded native `/navigate` pages (50 items), and six native presets; keep XML validation and opaque identity rules. Current parser reduces type to directory/non-directory and the browser response does not expose full playlist capability information. |
| `app/core/favorites.py` and `app/api/favorites.py` | Speaker-bound 900-second browse tokens, preset plan/confirmation, durable unknown intent, whole-map readback; overview already returns six numbered slots with names/Empty. Reuse these rather than inventing slot-readout functionality. |
| `app/core/models.py`, `app/api/routes.py` | Station/favorite/AUX/preset schedule fields, existing source exclusivity checks and preset-1 legacy default; no durable collection binding. An unrecognized added collection field can be ignored and defaulted: add authoritative source recognition rather than merely sending new UI fields. |
| `app/scheduler/jobs.py` | Configuration normalization, serialized mutations/persistence, queueing, runtime and occurrence handling; extend normalization AND dispatch so durable collection data survives a restart. |
| `app/core/playback.py:run_on`, `app/core/control.py` | NAS schedule execution currently recalls a preset; radio uses direct select through guarded ownership/identity/volume-zero flow. Reuse selection and safeguards for direct collections without making collection schedules into station or favorite records. |
| `app/core/speaker_cache.py` | Existing 15-second snapshot validity; keep it for normal status refresh. |
| `app/templates/index.html`, `app/static/presets.js`, `app/static/stations.js` | Existing home, editor, station library, playback states and preset view. Compose/relabel these; current preset browser is not proof of first-class playlist behavior. |
| `tests/test_library.py`, `tests/test_favorites.py`, `tests/test_routes_validation.py`, `tests/test_scheduler_jobs.py`, `tests/test_playback_operations.py`, UI tests | Extend existing contract fixtures and harnesses; do not treat test fixtures as hardware evidence. |

User-confirmed existing immediate NAS playback is a preservation requirement, not a new product capability. Static inspection specifically establishes that the schedule path is preset-based and needs an additive direct-source seam. No runtime capability claims were inferred from a generic directory fixture.

Relevant main specs were read in full. `nas-library-and-native-presets` currently restricts offered items to playable AND preset-capable; its delta separates browsing, playback and assignment eligibility. `schedule-management-and-execution` retains a legacy default of button 1; the delta preserves old source-less records while refusing that fallback for explicit collections. `docs/calm-schedule-ux.md` currently buries music in Settings and proposes schedule-first browsing; this accepted shared Music flow supersedes those recommendations. Existing `add-everyday-radio-listening` already supersedes the older main-spec volume-5 everyday-radio scenario; retain its chosen-volume/session Stop contract. Relay recovery and unsupported-service removal changes remain untouched.

## Goals / Non-Goals

**Goals:** Keep the current ownership, quiet-start, independent-speaker and schedule engine boundaries while adding durable collection intent and native library lifecycle observations. Keep each capability owned by one delta; the UI references those behaviors instead of duplicating their backend rules.

**Non-Goals:** Implementation in this turn, prototype/mockup, device commands, live or production tests, replacement Bose/Marge service, redirects/cloud clones, NAS mounts/audio proxy, firmware changes, new playlist editor/shuffle, individual-track actions, multiroom or broad scanner. No commit/push, spec sync or archive.

## Decisions

### 1. Shared catalog with per-speaker observations

Persist a stable library identity with its user-visible name and observed per-speaker registration/source account, availability and observation time. Keep transient discovery separate from added registrations. Use the existing persisted store beside configuration where practical, with an additive section and atomic preservation of old records; do not create a parallel persistence subsystem. Shared UI identity never confers target access. Deduplicate stable IDs, not names, IP addresses or browse-session tokens. Keep stale/offline observations visibly distinct from current evidence.

Discovery first asks each known, identity-verified speaker for `/listMediaServers`. An empty list offers Search Again and network/media-service guidance; no independent scanner is required. Native add uses the discovered stable server identity and selected speaker. Native remove uses the EXACT registered source account read from that speaker, not its display name. The account for Add is derived by stripping one `uuid:` prefix and using UUID plus `/0`; do not repeatedly normalize or substitute this derived value for an observed removal account.

Use supported-URL checks, bounded transport and XML result validation even for HTTP success. For STORED_MUSIC, native credentials carry the source, displayName, user and an empty pass for both operations. After mutation, observe sources on all known speakers. Unknown speakers remain pending reconciliation; independent versus propagated registration is a firmware observation, not an architecture assumption. No bulk propagation writes or re-adds follow observation.

Alternatives rejected: a speaker-owned library model leaks browse implementation into UX; a private scanner adds infrastructure without establishing speaker access; a replacement Bose/Marge server changes scope without solving black-box firmware qualification.

### 2. Resolve durable collection intent at the target

Add an explicit direct-collection source discriminator and versioned binding, separate from station/favorite/AUX/preset modes. Store library stable ID, pinned target hardware ID, collection type/name, native source/account/location context and enough opaque ancestor-resolution context to re-resolve after token expiry or restart. Store native context as a candidate, not a promise that locations remain permanent or portable. Never use a temporary browse token, physical slot or raw DLNA objectID as the durable source.

On action selection and speaker change, find the target's observed registration, resolve the collection through that target's native hierarchy and verify identity/access. Re-resolve persisted context on due execution; accept an exact verified native identity only while still valid. An ambiguous duplicate name/path is unresolved, not a successful match. Renamed/moved/missing collections require replacement; fail closed rather than choose similar content. The UI can browse using a ready context speaker without assigning ownership to it.

Extend existing schedule validation, typed data, persistence normalization and playback dispatch together. Explicit collection/unsupported/conflicting payloads must be rejected before any preset default. Preserve omitted binding on old-client edits and reject conflicting edits. Existing valid records retain semantics without automatic source conversion. Direct selection reuses identity, volume zero before selection, current-owner checks, matched playback before fade, active-speaker politeness, cancellation and occurrence rules. OFF retains its established behavior; session-specific manual Stop cannot stop a replacement owner.

Alternative rejected: implementing Schedule by quietly assigning a spare button introduces capacity, overwrite and drift coupling. Storing only a folder display path or copying another speaker's token is unverifiable. A separate playback engine duplicates safeguards.

### 3. Separate collection capability axes and preserve browser state

Retain opaque native types and independent inspect/play/preset capabilities through parser/API/UI. A playlist and folder share the browser; known playlist type gets its own icon. Enumerability is independent from playability. A playable playlist without preview shows Preview unavailable with supported actions. Unknown type/capability does not get optimistic assignment. Real playlist browse, play, direct schedule and preset-capable assignment each need distinct later qualification; generic directory fixtures prove none of them.

Store view-local loaded pages, scroll and breadcrumb context by library/collection, rejecting stale asynchronous results after navigation. Reserve safe-area and dock/action height in content layout so the last row/Load more remain reachable. Row taps inspect only; tracks have inspect-only information. The accepted action area is a TRIAL above the dock, labelled with the inspected collection and Play / Schedule / Assign text. This supersedes the earlier top-actions recommendation. Phone layout/thumb-reach checks happen later, after implementation is separately authorized; no prototype or phone QA is produced now.

### 4. Explicit mutations, impact pauses and observation recovery

Extend existing mutation coordination rather than adding automatic write retries. For native add/remove keep selected target/library and durable pending/unknown intent sufficient to reconcile after crash. Timeout means readback before any offered write retry. Inconclusive readback stays Unknown with Check Again; conclusive evidence of non-execution allows explicit retry. Ready requires registration AND availability. Observe other speakers after each mutation, including when the acknowledgement is lost.

Before button replacement, compute known bound-favorite and legacy slot schedule impacts on that hardware ID/slot and warn. On confirmed replacement, persist their review pauses before issuing the button write; failure to persist blocks that write. Cancel has no pause effect. If the write outcome is unknown, retain pauses until review rather than risk a routine playing changed content. Reuse existing map fingerprint/expiry checks, write-ahead intent, duplicate-content safeguards and whole-map readback. Do not overwrite unrelated slots or auto-restore them. Optional Play now is a separate guarded action.

Before library removal, show known schedule/button impacts plus possible propagation and incomplete-observation warnings. Persist the removal intent, then reconcile schedules against observed source removals on all known speakers, pausing confirmed affected bindings and retaining pending reconciliation for offline speakers. Scheduled execution still checks source readiness while reconciliation is pending. Buttons may retain stale native references; explain them without rewriting. Retain shared library where any registration remains; remove the added-list entry only after observed absence everywhere known. Keep paused schedule recovery data even then.

Temporary outage is different: keep the library as Unavailable and leave ordinary routines unpaused; skip each unavailable due ON before source/volume writes, record reason, never fallback or catch up. Startup/Check Again observes return to Ready. Missing registration offers explicit Add Again. Explicit-removal/replacement pauses survive automatic observation recovery; Replace music retains all other editor settings, followed by explicit review/re-enable.

Trade-off: conservatively paused button schedules can require review after a failed replacement. This avoids executing against an uncertain slot and is visible in both UI and docs. Library propagation may leave partial/unknown observations; never report universal success while another speaker is unreadable.

### 5. Reuse global radio and session ownership for draft tests

Keep the global catalog and existing radio schedule selector. Add a transient unsaved station draft eligible for the existing URL validation, readiness and guarded radio test path; do not persist a visible station merely to run Test. Reuse bounded session descriptors and cleanup rather than creating a second radio transport. Keep the name/URL form visible with speaker choice and Stop/status. Bind test evidence to canonical URL, verified speaker and operation; URL changes invalidate evidence. Audible confirmation is the user's assertion, never inferred from HTTP acceptance or reported Playing. Enable Save only after that confirmation and a confirmed stopped test; name-only edits need not repeat a URL test.

Retain existing quiet-test constraints and separately consented experimental diagnostic limitations; unavailable/unsafe draft tests fail honestly. Normal saved-station Play retains explicit chosen listening volume, distinct from Test, without a diagnostic timer. Stop compares exact current operation/speaker identity and uses STOP-only semantics. Unknown Stop offers checking and cannot stop replacement audio. Existing saved stations, seed records, archives and schedules remain valid without retroactive test requirements. Save persists only after draft eligibility and does not start another session.

Alternative rejected: save-then-test violates the accepted workflow and leaves failed drafts in the global catalog; guessing audible success from readback is false evidence.

## Risks / Trade-offs

- Native registration may rely on firmware-internal services and return historical credential errors such as `1022 MARGE_SET_CRED_FAILED` -> show native failure and retained selection; no replacement service is in scope. Protocol evidence is not a hardware guarantee.
- Native collection identity can change -> conservative target resolution and missing-source recovery can block an action rather than play the wrong collection. Stable identity cannot be guaranteed by a display path.
- Playlist type/preview support varies -> preserve capability distinctions, qualify a real playlist separately, retain the accepted Preview unavailable exception.
- Readback across offline speakers is incomplete -> retain unknown observations and reconcile later; warnings state possible propagation and known versus unknown impacts.
- New binding/pause metadata must survive normalization and restart -> additive persistence round-trip tests, unknown-source rejection and explicit rollback limitations.
- Phone action area consumes vertical room -> reserved layout space, accessible labels and later real phone/thumb checks. This is the accepted trial, not visually qualified today.
- Audible test is a manual observation -> software can enforce lifecycle and user acknowledgement but cannot establish actual sound or compatibility itself.

## Migration Plan

After separate design approval, implement in the bounded milestones in `tasks.md`, using fixtures and network-disabled tests first. No automatic rewrite of existing schedules, presets or registrations. Additive durable data must preserve unrelated records atomically. Upgrade reads old stores; unsupported new source versions fail closed with an actionable reason.

Before deployment, back up schedule and favorites/library state together. Rolling back code after saving collection schedules requires disabling those schedules or restoring the pre-upgrade state: older code can discard unknown collection fields/default to a preset, so downgrading against new collection data is unsafe. Review-paused routines remain paused until explicit review; no rollback path silently reverses device registration or button writes. All deployment and hardware actions are outside this planning turn.

## Design Review and Evidence

Self-review against the accepted decisions: preserve working home/readout/playback; no library-speaker ownership assumption; no token portability; direct scheduling has an authoritative backend path and no preset fallback; assignment remains explicit/no autoplay; timeout reconciliation is read-first; removal never deletes files; temporary outages recover without silent registration or catch-up; explicit pauses survive recovery. No implementation blocker requires changing the accepted design. Firmware and playlist compatibility are qualification gates, not reasons to broaden architecture.

Primary community evidence re-read through GitHub Connector at immutable commit `7312711354c8b90f569574eaa906a2c887333ab3`:

- [Native discovery](https://github.com/gesellix/Bose-SoundTouch/blob/7312711354c8b90f569574eaa906a2c887333ab3/pkg/client/client.go#L324): speaker GET `/listMediaServers`.
- [Native account operations](https://github.com/gesellix/Bose-SoundTouch/blob/7312711354c8b90f569574eaa906a2c887333ab3/pkg/client/client.go#L2350): POST account add/remove and XML success/error handling; wrappers include STORED_MUSIC.
- [DLNA guide](https://github.com/gesellix/Bose-SoundTouch/blob/7312711354c8b90f569574eaa906a2c887333ab3/docs/content/docs/guides/dlna-music-library.md): speaker-produced navigate/select tokens, UUID account convention, source readiness and speaker-side discovery alternative. Its wider scanner/service features are not adopted.

Bundled `docs/reference/SoundTouch-Web-API.pdf` was identified locally; prior inspection supplied in the task reports MediaServer/Renderer on p7 and sources on p16, without a playlist/registration/portability contract. Those page claims were not re-extracted in this Windows pass and are not treated as newly verified evidence. `docs/native-presets.md` remains the source of current qualification limits. No real-speaker, audio, physical-button or phone visual result is claimed by these artifacts.

## Planning Validation (Windows, 2026-11-01)

- Pinned temporary OpenSpec CLI `1.14.3` used without changing repository dependencies.
- `openspec validate add-shared-music-library-workflows --strict --no-interactive`: valid.
- `openspec validate --all --strict --no-interactive`: 13 passed, 0 failed.
- `openspec status --change add-shared-music-library-workflows`: all four artifact categories complete; this means planning only.
- Five capability deltas contain 25 requirements and 63 scenarios; `tasks.md` contains 24 unchecked tasks and no completed implementation tasks.
- Tracked and staged Git diffs are empty. Only the new nine-file change directory is untracked. New-file `git diff --no-index --check` checks found no whitespace errors (Git emitted its normal LF-to-CRLF notices). HEAD remains `3796e57`.
- Final review restored explicit existing station URL exclusions and schedule field validation in the modified requirement blocks, avoiding loss of baseline constraints during later spec reconciliation.
- No application changes, runtime/production tests, prototype, live speaker/NAS action, commit/push, sync or archive occurred. Phone visual, native hardware and audible qualification remain pending future separate authorization. There is no planning blocker; design approval is the next gate before implementation.
