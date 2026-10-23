# Tasks

## 1. Remove new radio-to-preset assignment

- [x] 1.1 Add API tests proving `station_id`, `radio_url`, and non-NAS preset plans are rejected before durable intent, playback cancellation, or speaker writes; verify the focused favorites and route tests fail for the intended reason before implementation.
- [x] 1.2 Restrict physical-preset plan creation to playable, preset-capable items from a fresh READY `STORED_MUSIC` browse while retaining NAS preview, confirmation, whole-map concurrency, readback, and quiet-test behavior; verify the focused favorites and NAS-library tests pass.
- [x] 1.3 Remove the preset panel's Internet-radio form and the station action that assigns a physical button while retaining Play, Schedule, Remove, and the separately labelled direct diagnostic; verify the station and preset browser tests pass.
- [x] 1.4 Update user documentation to describe station Play and schedules as the supported radio path and new physical-preset assignment as NAS-only; verify documentation does not imply that Wisp clears or migrates existing speaker presets or legacy radio favorites.

## 2. Canonicalize station-backed schedules

- [x] 2.1 Add API tests for rejecting requests that combine station, favorite, numeric preset, or AUX playback kinds and for storing a station schedule with only `station_id` and pinned `speaker_id`; verify the focused schedule route tests fail for the intended reason before implementation.
- [x] 2.2 Resolve the playback kind before applying defaults, reject mixed kinds, and persist canonical station bindings while preserving older edits with omitted pinned identifiers and loaded legacy favorite-backed schedules; verify the focused route and scheduler tests pass.
- [x] 2.3 Add browser coverage showing that selecting a station schedule hides and omits favorite, preset, and AUX fields; verify station Play and physical NAS-preset controls remain available in their separate workflows.

## 3. Integration and evidence

- [x] 3.1 Run the complete automated test suite and strict OpenSpec validation, recording any unrelated pre-existing failure separately from regressions introduced by this change.
- [x] 3.2 Obtain independent review of the API rejection boundary, legacy-data compatibility, schedule normalization, and unchanged playback safety gates before applying or archiving the change.
- [ ] 3.3 After separate permission for real-speaker work, run supervised station Play and schedule qualification; report command acceptance, source/readback, and audibility as distinct evidence, and do not infer audible success from API state alone.

## 4. Correct the everyday Play affordance

The initial volume-5 affordance below was completed and tested as recorded. Its everyday listening semantics are superseded by `add-everyday-radio-listening`, which owns explicit volume, distinct diagnostic intent and session-specific Stop.

- [x] 4.1 Add a visible station-card Play button, naming the selected speaker and volume in confirmation, using the existing normal station endpoint without diagnostic fallback; keep the separately labelled test flow and its risk consent.
- [x] 4.2 Verify primary Play visibility, no autoplay before confirmation, speaker-change invalidation, unavailable-readiness refusal, and normal backend dispatch without the diagnostic timer; run isolated regression tests and strict specification validation.

Follow-up evidence: the network-disabled Linux suite passed 731 tests, JavaScript syntax and whitespace checks passed, and strict OpenSpec validation passed all 11 items. Real-speaker qualification remains pending under task 3.3.
