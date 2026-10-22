# Spec Delta

## MODIFIED Requirements

### Requirement: Validate and normalize schedule definitions
Wisp SHALL require a non-empty name, at least one valid weekday, `HH:MM` on/off times, volume from 0 through 100, and fade durations from 0 through 3600 seconds for API-created schedules. It SHALL reject combined station, favorite, preset, or AUX choices. An accepted station binding SHALL pin the speaker and store no favorite, preset, or source field; defaults apply only when no explicit playback kind is supplied.

#### Scenario: Invalid schedule is submitted
- **WHEN** a client submits malformed days, times, volume, fades, identifiers, or more than one station, favorite, preset, or AUX choice
- **THEN** Wisp returns field-specific validation errors and does not queue a configuration mutation

#### Scenario: Station schedule is accepted
- **WHEN** a client selects one saved station for a speaker and readiness succeeds
- **THEN** Wisp stores `station_id` and pinned `speaker_id` while clearing `favorite_id`, `preset`, and `source` from that schedule

#### Scenario: Existing pinned binding is edited by an older client
- **WHEN** an edit omits an existing `speaker_id`, `station_id`, or `favorite_id`
- **THEN** Wisp preserves the existing binding instead of silently weakening it

#### Scenario: Legacy favorite-backed schedule is loaded
- **WHEN** saved configuration contains an existing favorite-backed routine
- **THEN** Wisp preserves its current compatibility behavior without automatically converting it into a station schedule or rewriting a physical preset

