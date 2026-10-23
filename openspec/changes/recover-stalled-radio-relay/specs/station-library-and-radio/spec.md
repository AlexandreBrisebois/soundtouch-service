# Spec Delta

## ADDED Requirements

### Requirement: Recover only an exact disconnected relay
After an owned relay that reached speaker-reported Playing ends specifically because its speaker client disconnected, Wisp SHALL permit at most one automatic recovery attempt for the same in-memory logical operation. Eligibility SHALL expire after a bounded interval and SHALL not survive process shutdown or restart.

#### Scenario: Current relay client disconnects
- **WHEN** the exact current relay ends with `radio_client_disconnected` after reaching reported Playing and remains eligible through fresh validation
- **THEN** Wisp starts one bounded recovery attempt for the same operation without claiming that sound has resumed

#### Scenario: Relay ends for another reason
- **WHEN** relay startup, its volume gate, its upstream, or another transport step fails for any reason other than the eligible speaker-client disconnect
- **THEN** Wisp reports the failure or unknown outcome without starting recovery

#### Scenario: Recovered relay disconnects again
- **WHEN** the replacement relay ends after the operation has already used its one recovery attempt
- **THEN** Wisp reports the new disconnect as terminal unknown and does not attempt another recovery

#### Scenario: Wisp restarts after a disconnect
- **WHEN** Wisp shuts down or restarts before recovery completes
- **THEN** no recovery grant or automatic playback action survives the process boundary

### Requirement: Require fresh exact recovery evidence
Before any recovery write, Wisp SHALL freshly confirm the pinned speaker identity, current ownership, unchanged saved station URL, ungrouped state, exact prior Wisp relay URI and source, and expected actual and target volume. Missing, stale, changed, or ambiguous evidence SHALL invalidate recovery without selecting content.

#### Scenario: All recovery evidence matches
- **WHEN** fresh reads match the recovery grant's speaker, operation, station URL, prior relay URI, UPNP source, ungrouped state, and actual and target volume
- **THEN** Wisp may continue to the guarded volume-zero recovery sequence

#### Scenario: Speaker or content changed
- **WHEN** identity, ownership, station URL, source URI, source type, grouping, actual volume, or target volume differs or cannot be confirmed
- **THEN** Wisp declines recovery, sends no source-selection command, and does not affect any other speaker

### Requirement: Gate replacement audio at confirmed volume zero
An eligible recovery SHALL use a new peer-bound relay token. Wisp SHALL confirm actual and target volume zero before selecting the replacement URI, keep audio gated until the intended speaker connects at zero, and restore the selected target only through guarded writes after fresh matching playback evidence.

#### Scenario: Replacement relay recovers
- **WHEN** zero volume is confirmed, the intended peer connects to the new token, the gate is released, and fresh readback matches the replacement URI and reported Playing
- **THEN** Wisp closes the old resources, fades to the original selected target, and reports the same logical operation as recovered Playing with audible confirmation still false

#### Scenario: Zero volume is not confirmed
- **WHEN** either actual or target volume cannot be confirmed at zero
- **THEN** Wisp never selects the replacement URI or releases audio and ends recovery without restoring volume

#### Scenario: Recovery becomes ambiguous after a write
- **WHEN** a recovery command times out, returns an ambiguous result, or later evidence stops matching
- **THEN** Wisp closes only the attempted replacement resources, sends no automatic retry or POWER command, and reports a terminal unknown outcome
