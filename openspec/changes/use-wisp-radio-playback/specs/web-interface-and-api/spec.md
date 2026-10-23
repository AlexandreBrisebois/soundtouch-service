# Spec Delta

## MODIFIED Requirements

### Requirement: Keep supporting workflows separate and explicit
The UI SHALL expose station-library and native NAS-preset workflows as separate views and actions. Saving a station SHALL not imply playback, station Play and Schedule SHALL initiate Wisp-managed radio paths, and radio stations SHALL NOT be offered for physical-button assignment. NAS preset assignment SHALL retain its preview and confirmation, and play, remove, and direct-test actions SHALL retain distinct confirmations and risks.

#### Scenario: User saves a station
- **WHEN** the station form succeeds
- **THEN** the UI reports that no playback or preset changed and refreshes the library

#### Scenario: User opens station actions
- **WHEN** a speaker and saved station are selected
- **THEN** the station card exposes visible Play and Schedule buttons, and Play presents the selected station, speaker, and explicit listening volume as defined by `add-everyday-radio-listening` before requesting normal playback

#### Scenario: Everyday Play is unavailable
- **WHEN** the user chooses Play and readiness is unavailable or cannot be confirmed
- **THEN** the UI explains the failure without submitting playback or substituting an experimental direct test

#### Scenario: User changes speaker before confirming Play
- **WHEN** the selected speaker changes after opening the Play confirmation
- **THEN** the confirmation is invalidated and cannot start playback on either speaker until the user makes a fresh selection and confirmation

#### Scenario: Diagnostic remains separately available
- **WHEN** the user opens the station overflow menu
- **THEN** Test playback remains separately labelled and any experimental direct test retains its risk consent and ten-second limit; ordinary Play does not use that diagnostic path

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

