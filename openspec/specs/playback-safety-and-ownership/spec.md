# Playback safety and ownership Specification

## Purpose

Define conservative per-speaker control, evidence, cancellation, and volume sequencing so automation does not claim or continue playback without current ownership evidence.

## Requirements

### Requirement: Track explicit operation outcomes
Wisp SHALL track the latest in-memory operation per speaker with an ID, schedule name, state, reason, timestamps, terminal flag, and in-flight command flag. Terminal states SHALL be `playing`, `completed`, `skipped`, `unknown`, `failed`, or `canceled`; accepted or starting states SHALL NOT be represented as confirmed playback.

#### Scenario: Start request is accepted
- **WHEN** a worker begins checking a speaker
- **THEN** Wisp reports accepted or starting until fresh matching playback and final volume are confirmed

#### Scenario: Evidence is incomplete
- **WHEN** identity, command acknowledgement, content, playback state, or volume cannot be confirmed within the operation budget
- **THEN** Wisp ends the operation as unknown or failed and does not claim playback

### Requirement: Automatic starts remain polite
An automatic ON operation SHALL skip a speaker with fresh active playback and SHALL NOT use a blind POWER toggle when the state is unknown. A deliberate Run Now MAY replace current audio; only a deliberate manual start MAY use a fresh identity-matched unselected-idle exception.

#### Scenario: Scheduled start finds current audio
- **WHEN** a fresh read shows active speaker playback before an automatic selection
- **THEN** Wisp skips the operation without changing source or volume

#### Scenario: Speaker state is unknown
- **WHEN** current identity or transport state cannot be verified
- **THEN** Wisp sends neither a blind power toggle nor a source selection

### Requirement: Quiet starts require ordered confirmation
For normal preset, favorite, AUX, and supported station starts, Wisp SHALL verify the target identity, confirm volume zero before source selection, require fresh matching Playing evidence, and guard every fade-up write against current source, playback, ownership, and volume. Wisp SHALL stop rather than retry an ambiguous write.

#### Scenario: Matching playback is confirmed
- **WHEN** the selected content is freshly reported Playing and volume writes are confirmed
- **THEN** Wisp may fade toward the configured target and reports playing only after confirming the final volume

#### Scenario: Manual takeover occurs during fade
- **WHEN** fresh source, transport, or volume evidence no longer matches the owned operation
- **THEN** Wisp cancels remaining automation writes and does not restore or amplify the prior source

### Requirement: Serialize ownership and honor manual priority
Wisp SHALL allow one current operation per speaker. A new operation SHALL supersede the prior operation, while power, preset, and volume actions SHALL cancel automation before acquiring the per-device command lock. Cancellation SHALL prevent later reservations but SHALL allow an already reserved bounded command to finish.

#### Scenario: User cancels automation
- **WHEN** the cancel endpoint is invoked
- **THEN** Wisp invalidates pending work without sending STOP or POWER and tells the user that audio may continue

#### Scenario: Manual command follows an in-flight automation command
- **WHEN** automation already reserved a command before cancellation
- **THEN** that one command may complete, then the manual command runs after re-resolving and re-verifying the device

### Requirement: Apply explicit OFF ownership rules
A due non-radio schedule OFF SHALL fade and stop the speaker's current audio, including audio started manually after the ON event. A radio schedule OFF SHALL act only while its matching radio session still owns the speaker and SHALL not stop a replacement session.

#### Scenario: Non-radio OFF finds active audio
- **WHEN** a configured non-radio OFF time occurs and fresh state is active
- **THEN** Wisp fades toward zero and uses the bounded stop/power behavior defined by the current implementation

#### Scenario: Radio ownership changed
- **WHEN** an old radio OFF event no longer owns the speaker session
- **THEN** Wisp skips the stop and does not touch the new owner

### Requirement: Keep hardware claims qualified
Wisp SHALL treat speaker-reported Playing and confirmed protocol responses as evidence of device state, not proof of audible sound, firmware compatibility, or race-free physical-button interception.

#### Scenario: Offline tests pass
- **WHEN** mocked protocol and operation tests pass without authorized real-speaker testing
- **THEN** documentation and outcomes continue to identify audible playback and hardware compatibility as unverified

## Evidence

- Implementation: `app/core/playback.py`, `app/core/control.py`, `app/core/status.py`, `app/core/relay_playback.py`
- Contract tests: `tests/test_playback_operations.py`, `tests/test_control_responses.py`, `tests/test_radio_relay.py`
- Qualification limits: `docs/playback-reliability.md`

