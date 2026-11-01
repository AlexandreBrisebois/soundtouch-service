# NAS library and native presets Specification

## Purpose

Define read-only navigation of speaker-registered media sources and the explicit workflow for assigning content to one of a SoundTouch speaker's six physical preset buttons.

## Requirements

### Requirement: Browse only speaker-registered library sources
Wisp SHALL browse native opaque content in bounded pages through a speaker with a ready registration, preserving source, account, location and type. The library SHALL be shared rather than owned by that browse speaker. Browsing SHALL expose inspectable content; Play/Schedule eligibility SHALL depend on playability and Assign additionally on preset capability, independently verified for each target.

#### Scenario: User browses a NAS source
- **WHEN** a registered source and container are selected
- **THEN** Wisp sends opaque identifiers to the speaker that resolved them and parses each item's own ContentItem rather than a nested parent

#### Scenario: Browse response is malformed or ambiguous
- **WHEN** speaker XML cannot be validated or selected content identity is incomplete
- **THEN** Wisp fails closed without manufacturing a filesystem path or DLNA identifier

#### Scenario: A different action target is chosen
- **WHEN** a user browses through one speaker and chooses another for Play, Schedule or Assign
- **THEN** Wisp resolves and verifies that same collection against the target's registered source without assuming opaque identifiers are portable or registering a missing source
- **AND** failure preserves the selection with Retry or another-speaker recovery and no automatic target switch

### Requirement: Preview physical-button changes before writing
Wisp SHALL create a short-lived plan identifying the exact speaker, numbered slot, proposed collection/library and current six-slot map. It SHALL require explicit Assign or Replace Button N confirmation, and cancel on expiry, restart, identity change or competing map change. Replacement SHALL warn about affected existing button-based schedules and pause them for review before a write can proceed.

#### Scenario: User cancels a preview
- **WHEN** confirmation is canceled
- **THEN** no preset command or schedule pause is issued, all six buttons remain untouched by Wisp, and the previous browser state is restored

#### Scenario: Current map changed after preview
- **WHEN** any preset differs from the previewed map at confirmation time
- **THEN** Wisp rejects the write rather than overwriting concurrent changes

#### Scenario: User reviews an assignment
- **WHEN** a target speaker is selected for Assign
- **THEN** the existing readout shows six numbered slots with current content or Empty and review identifies collection, library, speaker, slot and old content
- **AND** the final button explicitly says Assign or Replace Button N

#### Scenario: Replacing a scheduled button
- **WHEN** the user confirms a replacement with known button-based schedules
- **THEN** Wisp durably pauses affected bound and legacy slot schedules with a review reason before sending the write, and keeps them paused if the write becomes uncertain
- **AND** direct collection schedules are unaffected and a pause-persistence failure prevents the button write

### Requirement: Persist intent and verify the whole preset map
Before issuing an approved store-preset command, Wisp SHALL durably record an unknown intent. It SHALL not blindly retry an ambiguous command, and afterward SHALL require the chosen slot to match and all other slots to remain unchanged before reporting `readback_matched`.

#### Scenario: Store response or readback is uncertain
- **WHEN** the command acknowledgement or fresh six-slot readback is missing or mismatched
- **THEN** Wisp retains an unknown result and does not claim that the button works or produces audible sound

### Requirement: Bind scheduled favorites to speaker, slot, and content
A confirmed native favorite SHALL pin the speaker device ID, button number, and expected content identity. A favorite-backed routine SHALL fail closed if the speaker is replaced, the button drifts, or the registered source is unavailable; it SHALL NOT follow replacement content silently.

#### Scenario: Another controller changes the saved button
- **WHEN** a scheduled favorite's slot no longer matches its stored content identity
- **THEN** Wisp changes neither source nor volume and reports the start as unready or unknown

### Requirement: Require deliberate quiet tests
Wisp SHALL start a native favorite test only after explicit confirmation, at target volume 5 with a two-second fade, and SHALL describe acceptance and speaker-reported playback separately from audible sound.

#### Scenario: Favorite test is accepted
- **WHEN** the binding is still valid and the background worker accepts the request
- **THEN** Wisp returns 202 and uses the ordinary quiet-start and ownership guards

### Requirement: Inspect collections without implicit playback
V1 SHALL support folders and playlists while individual tracks remain inspect-only. A row tap SHALL open contents or track information without playing. Known playlists SHALL be distinguishable by type/icon. Ordering SHALL remain server/speaker-owned without playlist editing, reordering or new shuffle behavior.

#### Scenario: User opens a collection
- **WHEN** a folder or browsable playlist row is tapped
- **THEN** Wisp displays its name, path and contents without any playback, schedule or assignment write

#### Scenario: Playlist cannot expose a contents preview
- **WHEN** the speaker marks a playlist playable but cannot enumerate its contents
- **THEN** Wisp shows Preview unavailable, retains supported Play/Schedule/Assign actions, and does not label it Empty

#### Scenario: Content capabilities differ
- **WHEN** a collection is playable but not preset-capable, or a track is inspected
- **THEN** Play/Schedule remain available for the collection, Assign explains its unsupported capability, and the track has no V1 action to play/schedule/assign individually

### Requirement: Play the inspected collection deliberately
Immediate NAS Play SHALL reuse existing playback and volume safeguards after target access verification, show source and speaker, and explain replacement of current playback. It SHALL retain accepted/starting/failure states until matching playback is observed, then show Playing on the named room with session-bound Stop on the same screen.

#### Scenario: User plays a collection
- **WHEN** the user confirms the shown source and target and access verification succeeds
- **THEN** Wisp plays immediately using the existing guarded path without assigning a button or saving a schedule

#### Scenario: Playback fails or Stop becomes stale
- **WHEN** a Play fails or an old Stop targets a replaced session
- **THEN** Wisp preserves collection and target for explicit Retry/other speaker, reports the reason, and cannot stop replacement audio or switch speakers automatically

### Requirement: Keep assignment separate from playback
Assignment SHALL reuse durable intent, concurrent-map checks and whole-map readback. Success SHALL not start audio; Play now SHALL be a separate optional action. Unknown results SHALL offer readback before another write and SHALL not imply hardware recall or audible success.

#### Scenario: Assignment is readback matched
- **WHEN** the chosen slot matches and all other slots are unchanged
- **THEN** Wisp shows the new slot content and offers optional Play now without starting playback automatically

#### Scenario: Acknowledgement or collateral readback fails
- **WHEN** assignment acknowledgement is ambiguous or another slot changed
- **THEN** Wisp retains an unknown result, preserves affected schedule pauses, and requires inspection before retry without automatic restoration or overwrites

## Evidence

- Implementation: `app/core/library.py`, `app/core/favorites.py`, `app/api/favorites.py`, `app/core/playback.py`
- Contract tests: `tests/test_library.py`, `tests/test_favorites.py`, `tests/test_playback_operations.py`, `tests/test_presets_ui.py`
- Qualification limits: `docs/native-presets.md`

