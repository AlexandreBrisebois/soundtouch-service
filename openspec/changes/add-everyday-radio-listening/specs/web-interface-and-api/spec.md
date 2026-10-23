# Spec Delta

## ADDED Requirements

### Requirement: Present everyday listening controls
Station cards SHALL expose normal Play for the selected speaker. Its listening form SHALL show the station, speaker, editable volume, and Play action. A fresh verified volume MAY prefill the form; unavailable volume SHALL require explicit selection. Diagnostics SHALL retain their separate labels and consent.

#### Scenario: Fresh volume is available
- **WHEN** the user opens normal Play and the selected speaker identity and live volume are verified
- **THEN** the listening form prefills that volume and allows editing before submission

#### Scenario: Volume cannot be read
- **WHEN** readiness succeeds but a fresh listening volume cannot be obtained
- **THEN** the UI leaves volume unselected and requires a valid explicit value without silently choosing test volume 5

#### Scenario: Speaker changes during preparation
- **WHEN** the user changes speaker or leaves the view while options are loading or a listening form is open
- **THEN** stale responses and confirmations cannot start playback on either speaker

### Requirement: Present truthful listening state
Wisp SHALL distinguish checking, accepted, starting, playing reported by the speaker, stopped, and failed or unknown outcomes. Its session Stop control SHALL bind the displayed speaker, station and operation. Normal listening SHALL NOT display test-only risk consent or claim audibility from API acceptance.

#### Scenario: Play is accepted
- **WHEN** normal Play returns an accepted operation
- **THEN** Wisp opens the selected speaker status and polls its outcome without saying that audible playback is confirmed

#### Scenario: Identity cannot be verified
- **WHEN** discovery identity is missing, live verification is unavailable, or live identity differs
- **THEN** Wisp gives the corresponding refresh, connectivity, or changed-device message without issuing playback or suggesting a blind wake toggle
