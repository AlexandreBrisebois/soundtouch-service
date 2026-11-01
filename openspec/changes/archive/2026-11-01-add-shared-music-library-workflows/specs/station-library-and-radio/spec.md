# Spec Delta

## MODIFIED Requirements

### Requirement: Maintain a local station library
Wisp SHALL store named canonical HTTP(S) direct-stream URLs globally, separately from presets. It SHALL reject credentials, query strings, fragments, invalid schemes, duplicate active URLs and bounded-store violations. Listing SHALL require no speaker. New drafts SHALL require deliberate testing and user confirmation of audible sound on a chosen speaker before Save; saving SHALL not consume a preset.

#### Scenario: Station is saved
- **WHEN** a valid unique name and direct-stream URL have completed the draft test and audible confirmation
- **THEN** Wisp stores the station globally without starting new playback or changing a speaker preset

#### Scenario: Station is removed
- **WHEN** removal is explicitly confirmed
- **THEN** Wisp hides it while retaining private metadata needed by existing schedules, favorites or playback without stopping audio or clearing a button

#### Scenario: Existing stations are opened
- **WHEN** the user opens Radio or the existing radio schedule selector
- **THEN** existing and newly saved global stations are available without selecting a NAS library or re-testing existing records

## ADDED Requirements

### Requirement: Test a station draft before saving
Add Station SHALL show name and URL fields without directory/search. Test SHALL explicitly choose a speaker, explain playback replacement and use existing safe test/playback and session-bound Stop semantics. Wisp SHALL keep fields visible, retain them on failure and require Stop completion before enabling Save after audible user confirmation.

#### Scenario: User completes an audible test
- **WHEN** matching playback is reported, the user confirms hearing the intended station, and the tested session is stopped
- **THEN** Save becomes available for that tested URL without claiming that reported playback alone proves sound

#### Scenario: User edits the URL or test fails
- **WHEN** the stream URL changes after testing, testing fails, or a Stop outcome is unknown
- **THEN** Wisp retains the form, clears stale test eligibility as appropriate, explains the failure and offers explicit retry/checking or another speaker without saving automatically

#### Scenario: Station is untested
- **WHEN** a new draft is submitted without a completed stopped test and audible confirmation
- **THEN** Wisp rejects Save with a field/action explanation rather than persisting an untested new station

### Requirement: Keep global radio Play and Schedule distinct
Radio Play SHALL select a target speaker and play immediately with explicit source/target and existing volume safeguards. Schedule SHALL open the existing editor separately with the station selected. Playback status and Stop SHALL remain on the initiating screen, and failures SHALL preserve station/target with Retry or other-speaker recovery.

#### Scenario: User plays an existing station
- **WHEN** Play is confirmed for the shown station, speaker and listening volume
- **THEN** Wisp reuses ordinary radio playback, shows accepted/starting and then Playing on the named room only after matching evidence, with session-bound Stop

#### Scenario: User schedules a newly saved station
- **WHEN** Schedule is chosen from global Radio
- **THEN** the existing editor offers that station directly alongside existing stations without a Music Libraries hop, new preset or playback action
