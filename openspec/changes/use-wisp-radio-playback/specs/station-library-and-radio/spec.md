# Spec Delta

## MODIFIED Requirements

### Requirement: Prefer native radio before gated relay playback
Wisp SHALL offer manual station Play and station-backed schedules without requiring a free physical preset, `/storePreset`, or a READY `LOCAL_INTERNET_RADIO` source. Wisp SHALL use native `/select` when that source is READY and otherwise use an eligible gated relay. Both modes SHALL retain the existing ownership, cancellation, identity, volume, and per-speaker isolation guards.

#### Scenario: Native radio is ready for a non-relay URL
- **WHEN** the speaker reports READY `LOCAL_INTERNET_RADIO` and `/select` while the saved URL is not supported by the relay
- **THEN** readiness selects native mode and does not reject the URL for relay incompatibility

#### Scenario: Native radio is unavailable but relay is ready
- **WHEN** the speaker lacks READY `LOCAL_INTERNET_RADIO` and the saved station and speaker-reachable Wisp origin satisfy relay readiness
- **THEN** Wisp allows manual Play and station-backed schedule selection without inspecting or changing any physical preset

#### Scenario: Relay prerequisites are missing
- **WHEN** native radio is unavailable and the base URL is absent or unsafe, the source has no supported relay adapter, or the target cannot use the relay
- **THEN** readiness explains the failure and no stream or speaker command is started

#### Scenario: Manual station playback is confirmed
- **WHEN** the user confirms playback, readiness succeeds, and the operation is accepted
- **THEN** Wisp uses target volume 5 and the standard ownership/cancellation guards without writing a physical preset

#### Scenario: Scheduled station starts
- **WHEN** a due station-backed schedule passes readiness and starts playback
- **THEN** Wisp creates an operation for that speaker and station without recalling or writing a physical preset

## ADDED Requirements

### Requirement: Exclude radio from physical preset assignment
Wisp SHALL NOT offer or accept new radio-to-physical-preset assignments. Removing that workflow SHALL NOT clear, rewrite, migrate, or automatically recall existing speaker presets or stored legacy radio-favorite records.

#### Scenario: Station actions are presented
- **WHEN** a user opens the actions for a saved radio station
- **THEN** Wisp offers Play and Schedule without an Assign to speaker button action

#### Scenario: Legacy radio favorite exists
- **WHEN** Wisp loads data containing an existing radio favorite or a speaker reports an existing radio preset
- **THEN** Wisp preserves the record and speaker state without creating a new assignment or performing an automatic migration

