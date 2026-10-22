# Schedule management and execution Specification

## Purpose

Define the persisted routines that make Wisp's primary experience: starting and stopping selected audio at local wall-clock times with explicit volume and fade behavior.

## Requirements

### Requirement: Validate and normalize schedule definitions
Wisp SHALL require a non-empty name, at least one valid weekday, `HH:MM` on/off times, volume from 0 through 100, and fade durations from 0 through 3600 seconds for API-created schedules. It SHALL reject AUX combined with a preset and SHALL reject a saved station combined with a saved favorite. When neither AUX nor a preset is supplied, preset 1 SHALL be the default; an accepted station or favorite binding SHALL canonicalize the stored preset/source fields for that binding.

#### Scenario: Invalid schedule is submitted
- **WHEN** a client submits malformed days, times, volume, fades, identifiers, AUX with a preset, or a station with a favorite
- **THEN** Wisp returns field-specific validation errors and does not queue a configuration mutation

#### Scenario: Existing pinned binding is edited by an older client
- **WHEN** an edit omits an existing `speaker_id`, `station_id`, or `favorite_id`
- **THEN** Wisp preserves the existing binding instead of silently weakening it

### Requirement: Manage schedules asynchronously
Wisp SHALL list schedules and accept add/update, rename, delete, pause, and resume mutations through a serialized configuration queue. Paused schedules SHALL remain visible and editable but SHALL be skipped by automatic execution.

#### Scenario: Schedule mutation is accepted
- **WHEN** a valid schedule mutation is submitted
- **THEN** the API returns 202 and the configuration worker applies it sequentially to disk and memory

#### Scenario: Schedule is renamed
- **WHEN** an update supplies a previous name different from the new name
- **THEN** Wisp removes both conflicting old/new entries and persists one normalized schedule under the new name

### Requirement: Execute each due local occurrence at most once
Wisp SHALL evaluate schedules against the server-local timezone once per observed wall-clock minute and SHALL execute matching ON and OFF events only on selected weekdays. Wisp SHALL not catch up missed minutes, SHALL skip nonexistent spring-forward times, and SHALL run a repeated fall-back wall minute at most once per local date and process.

#### Scenario: A due minute repeats
- **WHEN** the scheduler observes the same local date, minute, speaker, schedule, and event more than once
- **THEN** it queues that occurrence only once

#### Scenario: Service was unavailable during a scheduled minute
- **WHEN** the scheduler next observes a later wall-clock minute
- **THEN** it does not replay the missed occurrence

### Requirement: Expose runtime timing separately from saved configuration
Wisp SHALL compute each schedule's next pending ON or OFF occurrence with an offset-bearing timestamp and the server timezone, without modifying the saved schedule document.

#### Scenario: Client requests schedule runtime
- **WHEN** a client requests runtime data for a speaker
- **THEN** Wisp returns pause state, next occurrence, timezone, and the matching last operation outcome when available

### Requirement: Support deliberate immediate runs
Wisp SHALL allow a user to run an existing schedule immediately even when it is paused. Identical concurrent pending requests SHALL coalesce, a missing worker SHALL reject the run, and API acceptance SHALL state that playback is not yet confirmed.

#### Scenario: User selects Run Now
- **WHEN** the schedule exists and the playback worker accepts the operation
- **THEN** Wisp returns 202 with the accepted operation and uses force semantics that may replace current audio

## Evidence

- Implementation: `app/api/routes.py`, `app/scheduler/jobs.py`, `app/core/models.py`
- Contract tests: `tests/test_routes_validation.py`, `tests/test_scheduler_jobs.py`, `tests/test_playback_ui.py`

## Known gaps

- Cross-source validation is incomplete: API payloads can combine a station or favorite with AUX/preset fields and those fields are silently canonicalized rather than rejected.
- Loaded configuration can retain both `station_id` and `favorite_id`; current execution gives the station binding precedence. This documents present behavior for a future corrective change, not a desired permanent contract.

