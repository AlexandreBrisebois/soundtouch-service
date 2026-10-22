# NAS library and native presets Specification

## Purpose

Define read-only navigation of speaker-registered media sources and the explicit workflow for assigning content to one of a SoundTouch speaker's six physical preset buttons.

## Requirements

### Requirement: Browse only speaker-registered library sources
Wisp SHALL read sources from the selected speaker and browse their native opaque content hierarchy in bounded pages. It SHALL preserve source, source-account, location, and content type, and SHALL offer only content the speaker marks playable and preset-capable.

#### Scenario: User browses a NAS source
- **WHEN** a registered source and container are selected
- **THEN** Wisp sends the speaker's opaque identifiers back to that same speaker and parses each item's own ContentItem rather than a nested parent

#### Scenario: Browse response is malformed or ambiguous
- **WHEN** speaker XML cannot be validated or the selected content identity is incomplete
- **THEN** Wisp fails closed without manufacturing a filesystem path or DLNA identifier

### Requirement: Preview physical-button changes before writing
Wisp SHALL create a short-lived plan that identifies the exact speaker, target slot, proposed content, and current six-slot map. It SHALL require a separate explicit confirmation and SHALL cancel the plan on expiry, restart, identity change, or a competing preset-map change.

#### Scenario: User cancels a preview
- **WHEN** the confirmation is not sent
- **THEN** no preset command is issued and all six physical buttons remain untouched by Wisp

#### Scenario: Current map changed after preview
- **WHEN** any preset differs from the previewed map at confirmation time
- **THEN** Wisp rejects the write rather than overwriting concurrent changes

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

## Evidence

- Implementation: `app/core/library.py`, `app/core/favorites.py`, `app/api/favorites.py`, `app/core/playback.py`
- Contract tests: `tests/test_library.py`, `tests/test_favorites.py`, `tests/test_playback_operations.py`, `tests/test_presets_ui.py`
- Qualification limits: `docs/native-presets.md`

