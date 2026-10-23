# Spec Delta

## ADDED Requirements

### Requirement: Preserve ownership across listening Stop
Accepting Stop SHALL atomically compare the current operation and transfer only its matching radio ownership to a bounded stop operation. Every device write SHALL retain fresh identity and source checks. Replacement or cancellation SHALL prevent further old stop writes. Other speakers SHALL remain independent.

#### Scenario: Replacement happens while Stop is queued
- **WHEN** a new operation replaces an accepted Stop before its worker runs
- **THEN** that stale worker performs no device write

#### Scenario: Independent speaker is listening
- **WHEN** a user stops one speaker's session
- **THEN** another speaker's stream, ownership and volume remain unchanged

#### Scenario: Current content no longer matches
- **WHEN** live source evidence no longer matches the listening session
- **THEN** Stop ends without sending STOP or POWER to replacement content
