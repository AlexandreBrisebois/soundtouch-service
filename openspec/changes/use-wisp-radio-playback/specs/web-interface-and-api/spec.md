# Spec Delta

## MODIFIED Requirements

### Requirement: Keep supporting workflows separate and explicit
The UI SHALL expose station-library and native NAS-preset workflows as separate views and actions. Saving a station SHALL not imply playback, station Play and Schedule SHALL initiate Wisp-managed radio paths, and radio stations SHALL NOT be offered for physical-button assignment. NAS preset assignment SHALL retain its preview and confirmation, and play, remove, and direct-test actions SHALL retain distinct confirmations and risks.

#### Scenario: User saves a station
- **WHEN** the station form succeeds
- **THEN** the UI reports that no playback or preset changed and refreshes the library

#### Scenario: User opens station actions
- **WHEN** a speaker and saved station are selected
- **THEN** the UI offers Play and Schedule without displaying an Assign to speaker button action

#### Scenario: User selects station Schedule
- **WHEN** the station action opens the schedule editor
- **THEN** the radio station is selected without displaying irrelevant favorite, preset, or AUX controls or submitting any non-null competing playback choice; null clearing fields MAY be sent for edit compatibility

#### Scenario: User manages NAS presets
- **WHEN** the user opens the physical-preset workflow
- **THEN** Wisp continues to offer speaker-registered NAS content with the existing preview and explicit confirmation safeguards

## ADDED Requirements

### Requirement: Reject new radio preset plans
The HTTP API SHALL reject station identifiers, radio URLs, and non-NAS content submitted as new physical-preset plans. Rejection SHALL occur before durable intent, preset programming, playback, or any other speaker write.

#### Scenario: Client submits a station preset plan
- **WHEN** a client sends `station_id` or `radio_url` to the preset-plan endpoint
- **THEN** Wisp returns a validation error and leaves all six speaker presets unchanged

