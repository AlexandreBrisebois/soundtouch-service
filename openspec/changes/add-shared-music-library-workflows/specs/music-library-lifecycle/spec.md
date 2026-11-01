# Spec Delta

## Purpose

Manage shared NAS music libraries through speaker-native discovery and explicit registration/removal, with truthful per-speaker availability and recovery.

## ADDED Requirements

### Requirement: Discover libraries through speakers
Wisp SHALL use speaker-native media-server discovery first and combine results by stable server identity, retaining speaker visibility. Discovery SHALL not register sources or require an independent NAS scanner. Display-name equality alone SHALL not merge libraries.

#### Scenario: Several speakers see the same NAS
- **WHEN** Add Library discovers the same stable server ID through several speakers
- **THEN** one result shows its observed speaker visibility and preserves distinct same-name servers with different IDs

#### Scenario: No server is visible
- **WHEN** discovery returns no results or bounded reads fail
- **THEN** Wisp distinguishes no results from failure, offers Search Again and music-service/network guidance, and retains the selected speaker

### Requirement: Add only through explicit native registration
Add Library SHALL retain the selected NAS and target speaker, preselecting context when present. It SHALL show Adding then Checking availability. Ready SHALL require observed registration and availability on that speaker. Unsupported native operations or device XML errors SHALL explain failure without claiming success.

#### Scenario: Add succeeds but source is unavailable
- **WHEN** the source is observed registered after Add but is not available
- **THEN** Wisp shows Added, Unavailable with Check Again and preserves the library; it does not present Ready or start playback

#### Scenario: Registration becomes ready
- **WHEN** registration and availability are both observed for the chosen speaker
- **THEN** Wisp shows Ready and Browse without requiring assignment to a button

#### Scenario: Firmware rejects registration
- **WHEN** the native API is unsupported or reports an error even with HTTP success
- **THEN** Wisp preserves the selection and shows the concrete error and recovery action without adding a ready source

### Requirement: Reconcile uncertain mutations before retry
After a registration or removal timeout, Wisp SHALL reread registration before offering a mutation retry. An unresolved result SHALL remain Unknown with a read-only check action; it SHALL NOT trigger a blind write retry. User selection SHALL survive failed or uncertain operations.

#### Scenario: Add response is lost
- **WHEN** registration times out but readback finds the source registered
- **THEN** Wisp reports its observed readiness without repeating Add

#### Scenario: Removal response and readback are unavailable
- **WHEN** neither the removal result nor source readback is conclusive
- **THEN** Wisp reports Unknown, preserves known state and offers checking rather than repeating Remove

#### Scenario: Readback proves mutation did not take effect
- **WHEN** a fresh conclusive read shows the requested registration state was not reached
- **THEN** Wisp offers an explicit user retry with the same selection and no automatic write

### Requirement: Observe registration independently across speakers
Wisp SHALL track Not registered, Registered unavailable and Ready per speaker and library. It SHALL reread all known speakers after library mutations and display inaccessible observations as unknown/stale. It SHALL accommodate independent or propagated registrations without assuming either model or issuing propagation writes.

#### Scenario: Firmware propagates a change
- **WHEN** adding or removing through one speaker changes registrations on other speakers
- **THEN** Wisp displays observed results for each and reconciles their known impacts without silently re-adding a removed registration

#### Scenario: Speaker observations disagree
- **WHEN** a library is Ready on one speaker and unavailable or not registered on another
- **THEN** the shared library remains visible and action eligibility reflects the chosen target speaker

### Requirement: Remove a registration with impact review
Remove SHALL be a secondary library action requiring a speaker, known schedule/button impacts, a possible-propagation warning and explicit confirmation. Wisp SHALL use the exact registered source identity, remove no music files, overwrite no buttons, and verify native removal by rereading speakers.

#### Scenario: User confirms removal
- **WHEN** the reviewed native removal is observed on affected speakers
- **THEN** Wisp pauses affected schedules with a reason and Replace music recovery, retains their settings, and retains the library wherever still registered

#### Scenario: Impact cannot be fully read
- **WHEN** an affected speaker cannot be observed during review or post-removal reconciliation
- **THEN** Wisp labels its impacts unknown rather than claiming a complete impact list or universal removal, retains pending reconciliation, and pauses newly confirmed affected schedules when observations arrive

#### Scenario: Last registration is removed
- **WHEN** fresh observations confirm no known speaker retains a registration
- **THEN** Wisp removes the library from the added list while keeping paused schedule references and allowing later explicit discovery/Add Again

#### Scenario: User cancels removal
- **WHEN** confirmation is canceled
- **THEN** no removal, pause or physical-button write occurs and the library browser remains available

### Requirement: Recover observations without silent registration
Wisp SHALL retain previously added libraries through offline periods and restart, recheck on startup and Check Again, and restore Ready only when observed. Missing registration SHALL show Not registered and explicit Add Again. Observation recovery SHALL NOT register sources or resume schedules paused by explicit removal.

#### Scenario: Temporary NAS outage ends
- **WHEN** a retained registered library becomes available again
- **THEN** it returns to Ready and unpaused schedules remain eligible at their next normal occurrence

#### Scenario: Registration disappears or source is still offline after restart
- **WHEN** startup readback finds no registration or finds a registered unavailable source
- **THEN** Wisp respectively offers Add Again or Check Again, retains schedule bindings and explains the state without deleting the library or silently adding it

#### Scenario: Recovery interrupts browsing
- **WHEN** current library content cannot be restored after an outage or restart
- **THEN** Wisp retains recoverable browse state or returns to the library with an explanation and a recovery action
