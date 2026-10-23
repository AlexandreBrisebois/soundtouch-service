# Spec Delta

## ADDED Requirements

### Requirement: Listen at an explicit chosen volume
Normal station Play SHALL require a selected speaker and integer listening volume from 0 through 100. It SHALL use the production native or guarded relay path and continue without a diagnostic listening timer. Quiet tests SHALL remain separate and use volume 5.

#### Scenario: Normal Play is accepted
- **WHEN** a user submits a ready station, matching speaker identity, and chosen volume
- **THEN** Wisp passes that volume through the existing guarded playback engine without invoking a diagnostic endpoint or ten-second timer

#### Scenario: Invalid volume or identity is submitted
- **WHEN** a Play request has a missing, boolean, fractional, or out-of-range volume or a changed speaker identity
- **THEN** Wisp rejects it before creating or canceling any playback operation

#### Scenario: Stream continues
- **WHEN** matching playback is established and the feed remains healthy
- **THEN** the session continues until explicit Stop, takeover, stream end, failure, or app shutdown rather than ending after a test interval

#### Scenario: A conflicting request is already pending
- **WHEN** a radio operation is still starting or stopping and a new request differs in station, speaker identity, listening volume, or diagnostic intent
- **THEN** Wisp rejects the conflict without canceling or changing the pending operation; only equivalent pending requests reuse its operation ID

### Requirement: Stop only the selected listening session
A radio Stop SHALL identify its station, speaker identity, and current operation. It SHALL refuse stale or replacement sessions before cancellation or device writes. It SHALL use verified STOP semantics and SHALL NOT send POWER.

#### Scenario: Stop targets the current session
- **WHEN** the exact owned playing session is stopped
- **THEN** Wisp stops that session and reports completed only after matching inactive or stopped readback

#### Scenario: Stop targets an older session
- **WHEN** a newer session replaced the operation named by Stop
- **THEN** Wisp rejects the request without canceling or stopping the new session or another speaker
