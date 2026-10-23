# Spec Delta

## ADDED Requirements

### Requirement: Report relay recovery honestly
The operation API and selected-speaker view SHALL distinguish recovery pending, recovering, recovered, declined, and failed outcomes. They SHALL identify protocol-reported recovery separately from audible confirmation and SHALL not expose private relay tokens, source credentials, or raw content identity.

#### Scenario: Recovery is in progress
- **WHEN** an eligible relay disconnect has started its one bounded recovery attempt
- **THEN** the selected speaker shows that Wisp is attempting recovery without saying audio is playing or audible

#### Scenario: Recovery reaches reported Playing
- **WHEN** fresh speaker and relay evidence satisfies the recovery contract
- **THEN** the UI reports protocol-level recovery while continuing to leave audible confirmation false

#### Scenario: Recovery is declined or fails
- **WHEN** recovery evidence changes, expires, is unavailable, or a bounded command remains ambiguous
- **THEN** the UI shows a concrete safe failure or unknown reason and does not imply that Wisp will retry

#### Scenario: User stops pending recovery
- **WHEN** the user submits Stop for the exact current listening operation while recovery is pending
- **THEN** the API accepts cancellation of that recovery, reports that no speaker STOP or POWER command was sent, and prevents a later automatic recovery write
