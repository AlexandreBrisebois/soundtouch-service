# Schedule management and execution Specification

## Purpose

Define the persisted routines that make Wisp's primary experience: starting and stopping selected audio at local wall-clock times with explicit volume and fade behavior.

## Requirements

### Requirement: Validate and normalize schedule definitions
Wisp SHALL require a non-empty name, at least one valid weekday, HH:MM on/off times, volume 0-100 and fade durations 0-3600 seconds for API-created schedules. It SHALL accept exactly one source mode: station, favorite, direct collection, AUX or preset. It SHALL reject conflicting or unsupported source data before persistence/execution. Legacy source-less schedules SHALL retain preset-1 compatibility; explicit collection requests SHALL never default to a preset.

#### Scenario: Invalid schedule is submitted
- **WHEN** days, times, volume, fades or identifiers are malformed, source modes conflict, or a source discriminator/binding is unsupported or incomplete
- **THEN** Wisp returns field-specific errors without queuing a mutation or creating a playback operation

#### Scenario: Existing pinned binding is edited by an older client
- **WHEN** an edit omits an existing speaker, station, favorite or collection binding
- **THEN** Wisp preserves the binding and rejects conflicts rather than silently weakening it or changing source mode

#### Scenario: Old configuration is loaded
- **WHEN** valid legacy station/favorite/AUX/preset or source-less configuration is loaded
- **THEN** its supported behavior remains intact without bulk rewriting or changing button assignments
- **AND** malformed or unsupported collection data is surfaced as invalid/unavailable and never sanitized into preset 1

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

### Requirement: Bind direct schedules durably to collections
A direct collection schedule SHALL retain library identity, intended folder/playlist, speaker hardware identity and sufficient native resolution data across restart and browse-token expiry. It SHALL execute that collection independently of physical buttons after verifying target access. Save SHALL neither play nor assign a button.

#### Scenario: User schedules inspected music
- **WHEN** Schedule is selected, the speaker is chosen if needed, and collection access is verified
- **THEN** the existing editor opens prefilled with collection name, library and speaker plus Change music, retaining days, times, volume, fades and existing radio selection capability
- **AND** Save persists the durable collection source without selecting audio or writing a physical preset

#### Scenario: Browser token expires or buttons change
- **WHEN** a direct collection schedule runs after restart, token expiry or unrelated button replacement
- **THEN** it resolves the bound collection on its verified speaker and directly selects it without recalling any preset

#### Scenario: Target speaker changes
- **WHEN** the user chooses a different speaker in the draft
- **THEN** Wisp revalidates the same collection on that speaker and blocks save until valid access is established, retaining the draft on failure

### Requirement: Preserve settings while replacing unavailable music
Editing a schedule with missing music SHALL show the unavailable source and Replace music. Selecting replacement music SHALL preserve its name, days, times, volume, fades and pause/review reason unless the user explicitly changes them. Review-paused schedules SHALL require explicit review and re-enable.

#### Scenario: User changes missing music
- **WHEN** an unavailable source is replaced and validated in the existing editor
- **THEN** other schedule settings remain intact and no playback, button assignment or automatic re-enable occurs

#### Scenario: User abandons replacement
- **WHEN** Change music is canceled
- **THEN** the intact draft and original unavailable binding return without saving a different source

### Requirement: Skip unavailable collection occurrences without substitution
A temporarily unavailable collection SHALL skip its due ON occurrence with a visible reason before source or volume changes. It SHALL NOT play another source, fall back to a button, pause/delete the routine or catch up later. The next normal occurrence SHALL recheck readiness under existing ownership and active-speaker safeguards.

#### Scenario: NAS is offline at ON time
- **WHEN** an unpaused direct collection schedule is due but its registration, access or collection cannot be verified
- **THEN** Wisp records a skipped/unavailable occurrence with reason, sends no selection or volume write, and leaves schedule settings and pause state intact

#### Scenario: NAS recovers after the missed occurrence
- **WHEN** availability returns after the due minute
- **THEN** Wisp does not start late and rechecks normally at the next occurrence

### Requirement: Preserve explicit impact pauses until review
Explicit library removal SHALL pause schedules whose bound source is confirmed removed on their speaker; confirmed button replacement SHALL pause affected button schedules as specified by NAS assignment. Wisp SHALL retain settings, show the reason and Replace music recovery, and require explicit re-enable. Automatic readiness recovery SHALL not clear these pauses.

#### Scenario: Registration returns after explicit removal
- **WHEN** a library becomes registered/ready again after a removal-related pause
- **THEN** the routine remains paused until reviewed and explicitly re-enabled

#### Scenario: Replacement affects only one button
- **WHEN** an approved replacement pauses routines using that speaker/button
- **THEN** direct collection routines and other speaker/button routines retain their settings and pause state

## Evidence

- Implementation: `app/api/routes.py`, `app/scheduler/jobs.py`, `app/core/models.py`
- Contract tests: `tests/test_routes_validation.py`, `tests/test_scheduler_jobs.py`, `tests/test_playback_ui.py`

## Known gaps

- Cross-source validation is incomplete: API payloads can combine a station or favorite with AUX/preset fields and those fields are silently canonicalized rather than rejected.
- Loaded configuration can retain both `station_id` and `favorite_id`; current execution gives the station binding precedence. This documents present behavior for a future corrective change, not a desired permanent contract.

