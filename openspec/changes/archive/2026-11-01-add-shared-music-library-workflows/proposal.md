# Proposal

## Why

Existing NAS playback, six-button readout, speaker controls and routines already work. Families need a phone-friendly way to inspect shared music first, then deliberately play, schedule or assign it, plus honest native NAS discovery, registration and removal.

## What Changes

- Add a Speakers / Music phone dock, with Radio and Music Libraries under Music. Preserve the home controls, schedules, immediate NAS playback and existing six-slot readout; keep Refresh Speakers and Turn All Off above the Speakers dock.
- Reorganize NAS browsing around a shared library and inspected folder/playlist, with target accessibility checked per action. Trial a text-labelled Play / Schedule / Assign area above the dock with reserved space. Row taps inspect, never play.
- Add durable direct-collection schedules independent of physical buttons and temporary browse tokens, reusing the existing editor, persistence queue and guarded playback. Reject unsupported/conflicting source payloads explicitly; never fall back to preset 1.
- Retain explicit six-button assignment preview, whole-map concurrency/readback and no autoplay; warn and pause affected existing button schedules for review on replacement.
- Add speaker-native media-server discovery and explicit add/remove with per-speaker registration/readiness observations, timeout readback and recovery. No replacement Bose/Marge service, redirects, cloud clone or firmware change.
- Keep Radio global. Add Station has name and URL only, with deliberate audible Test on a chosen speaker before Save, fields retained on failure, Stop then Save. Existing global saved stations and radio schedule selector remain available without a library hop.
- Document temporary-outage automatic recovery versus explicit-removal/replacement pauses. Keep folders/playlists in V1; tracks are inspect-only and playlist capabilities qualify independently.

## Capabilities

### New Capabilities

- `music-library-lifecycle`: Speaker-native discovery, shared stable library identity, explicit registration/removal and observed recovery across speakers.

### Modified Capabilities

- `nas-library-and-native-presets`: Shared collection inspection, capability-aware actions, target resolution and safe button replacement.
- `schedule-management-and-execution`: Additive durable collection sources, direct execution, source validation and reasoned skips/pauses.
- `station-library-and-radio`: Draft station test and audible user confirmation before Save, reusing radio safeguards.
- `web-interface-and-api`: Phone navigation, preserved home behavior, browse continuity and source-first Play / Schedule / Assign.

## Impact

Planning only in this change. Future implementation touches the existing library/favorites API and persistence seams, schedule model/validation/worker/playback, current UI assets and focused user docs/tests. No new runtime dependency is proposed. Existing station/favorite/AUX/preset schedules remain compatible; new collection data is additive and requires explicit source discrimination. Speaker ownership, volume-zero gates, cancellation, identity verification and session-bound Stop remain authoritative. Physical presets change only through explicit confirmed assignment; library registration/removal is also explicit and may propagate through firmware.

Current behavior was inspected statically at Windows HEAD `3796e57`. This proposal supersedes the browse-only-preset-capable restriction and preset-1 fallback for new collection requests, plus the hidden-settings music entry described in `docs/calm-schedule-ux.md`. It retains everyday radio volume/Stop behavior from `add-everyday-radio-listening` and relay recovery from `recover-stalled-radio-relay`; those existing changes are untouched. No phone visual QA, application runtime, device command, production test or audible qualification is claimed. Separate design approval is required before implementation; supervised hardware qualification requires separate authorization.
