# Proposal

## Why

The visible station Play button still uses the quiet test's fixed volume and confirmation. Families need normal listening with a chosen volume and a Stop action that applies only to the session they started.

## What Changes

- Select a saved station, speaker, and explicit volume from 0 through 100. Prefill volume only from a fresh identity-verified read; otherwise require the user to choose it.
- Separate everyday Play and quiet Test playback at the UI and API boundaries while reusing the existing guarded production playback engine.
- Expose continuous session status and an explicit Stop bound to the station, speaker identity, and operation ID. Stop uses STOP, never a POWER toggle, and cannot cancel a replacement owner.
- Distinguish missing discovery identity from unavailable or changed live identity. Retain all identity, ownership, volume-zero, cancellation, and speaker-isolation guards.
- Supersede the volume-5 everyday requirements in `use-wisp-radio-playback`; its no-radio-preset and schedule contracts remain unchanged. Keep the approved library refresh change intact.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `station-library-and-radio`: Explicit listening volume, production Play, separate diagnostics, and session-specific Stop.
- `web-interface-and-api`: Listening controls, fresh volume prefill, truthful session status and errors.
- `playback-safety-and-ownership`: Stale Stop refusal and STOP-only session control with existing safety boundaries.

## Impact

Touches station API/UI, playback queue and session lifecycle, tests, and focused specifications. No dependencies, physical presets, persisted configuration, or schedule semantics change. No automatic wake toggle is introduced. Offline tests establish software behavior; audible sound and hardware start/stop remain supervised qualification work.
