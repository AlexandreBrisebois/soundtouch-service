# Proposal

## Why

Wisp already has a station library, deliberate Play action, and station-backed schedules that can start radio without consuming one of a speaker's six preset buttons. Keeping a second radio-to-physical-preset workflow exposes unsupported readiness requirements and risks replacing working buttons, so radio should stay a Wisp-initiated playback choice while native preset management remains focused on speaker-registered NAS content.

## What Changes

- Keep saved-station Play and station-backed schedules as the supported radio experiences. Wisp may use a ready native radio source or its guarded relay path, but radio eligibility must not depend on a free physical slot, `LOCAL_INTERNET_RADIO`, or `/storePreset`.
- Remove radio station assignment from the physical-preset UI and reject new radio preset plans at the API boundary. Do not add a gabbo listener, marker preset, or physical-button bridge.
- Keep native NAS preset browse, preview, confirmation, whole-map readback, quiet testing, and favorite-backed schedule compatibility unchanged.
- Preserve existing speaker preset mappings and stored legacy radio-favorite records. Do not clear, rewrite, migrate, or automatically replay any physical preset.
- Make new station-backed schedules persist the station and pinned speaker identity without irrelevant favorite, preset, or AUX fields. Continue to use the existing playback ownership, volume gate, cancellation, source-readback, and per-speaker relay isolation safeguards.
- Keep the experimental direct UPnP test separate from normal manual and scheduled radio. This change does not promote its remembered-volume behavior into automation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `station-library-and-radio`: Make Wisp-initiated Play and schedules the radio product path and exclude physical radio preset assignment.
- `nas-library-and-native-presets`: Limit new Wisp physical-preset plans to speaker-reported NAS content while preserving existing preset state and compatibility.
- `schedule-management-and-execution`: Require station-backed schedules to use an exclusive station binding without preset, favorite, or AUX fields.
- `web-interface-and-api`: Remove radio preset-assignment affordances and reject radio preset-plan writes while leaving NAS preset workflows intact.

## Impact

- UI: station actions and the preset panel no longer offer radio-to-button assignment; station Play and Schedule remain available.
- API: preset-plan creation no longer accepts `station_id` or `radio_url` as new physical-preset content. Station Play, readiness, descriptor compatibility, and schedule endpoints remain.
- Runtime: radio playback continues through existing native selection or gated relay orchestration with no weakening of ownership or volume safety. Existing native NAS presets, legacy saved favorites, and speaker mappings are not rewritten.
- Scheduling: newly saved or edited station choices are represented by `station_id` plus pinned `speaker_id`; existing legacy configurations remain readable and are not migrated automatically.
- Evidence: removal and validation behavior can be covered offline. Audible playback, provider compatibility, and long-running relay behavior remain separate real-speaker qualification work.
