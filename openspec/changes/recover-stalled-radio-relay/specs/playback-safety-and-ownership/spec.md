# Spec Delta

## MODIFIED Requirements

### Requirement: Track explicit operation outcomes
Wisp SHALL track the latest in-memory operation per speaker with an ID, schedule name, state, reason, timestamps, terminal flag, in-flight command flag, and bounded recovery metadata when applicable. Terminal states SHALL be `playing`, `completed`, `skipped`, `unknown`, `failed`, or `canceled`; accepted, starting, recovery-pending, or recovering states SHALL NOT be represented as confirmed playback.

#### Scenario: Start request is accepted
- **WHEN** a worker begins checking a speaker
- **THEN** Wisp reports accepted or starting until fresh matching playback and final volume are confirmed

#### Scenario: Evidence is incomplete
- **WHEN** identity, command acknowledgement, content, playback state, or volume cannot be confirmed within the operation budget
- **THEN** Wisp ends the operation as unknown or failed and does not claim playback

#### Scenario: Relay recovery is pending
- **WHEN** an eligible relay disconnect has reserved recovery but replacement playback is not freshly confirmed
- **THEN** Wisp reports a nonterminal recovery state, attempt count, and reason without reporting Playing or audible confirmation

## ADDED Requirements

### Requirement: Let current ownership invalidate recovery
Recovery SHALL retain the original logical operation ID and SHALL proceed only while its recovery generation remains the current owner of the pinned speaker. Stop/OFF, cancellation, replacement, manual control, takeover, shutdown, or expiry SHALL invalidate unreserved recovery work before any later write.

#### Scenario: Exact Stop arrives while recovery is pending
- **WHEN** Stop names the current listening operation, speaker identity, and station before recovery reserves its next write
- **THEN** Wisp cancels recovery atomically, sends neither STOP nor POWER to the speaker, and reports that no speaker command was needed

#### Scenario: Matching schedule OFF arrives while recovery is pending
- **WHEN** the owning station schedule reaches OFF before recovery succeeds
- **THEN** Wisp invalidates recovery without selecting a replacement URI or stopping unrelated content

#### Scenario: Replacement wins before a recovery write
- **WHEN** another operation, user control, source takeover, shutdown, or expiry replaces or invalidates the recovery owner
- **THEN** the stale recovery performs no later speaker write and closes only resources it reserved

#### Scenario: In-flight recovery write was already reserved
- **WHEN** invalidation occurs after one bounded recovery command has been reserved
- **THEN** that command may finish, but fresh ownership validation prevents every subsequent write or gate release

#### Scenario: Recovery succeeds
- **WHEN** the same logical operation completes the guarded replacement sequence
- **THEN** its existing session-bound Stop and matching scheduled OFF ownership continue to apply to the new live relay lease
