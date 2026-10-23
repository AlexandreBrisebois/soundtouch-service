## ADDED Requirements

### Requirement: Show speaker-native library observations
The speaker overview SHALL display native preset slots separately from Wisp favorites, even when there are no Wisp favorites. It SHALL show sanitized service availability without raw account identifiers or account display names. Service summaries SHALL be informational and SHALL NOT enable non-NAS browsing or imply working playback.

#### Scenario: Speaker has presets and Spotify but no Wisp favorites
- **WHEN** the overview is loaded
- **THEN** native slots and Spotify availability are visible separately from the empty Wisp favorites list
- **AND** account identifiers remain private and NAS browsing retains its existing checks

### Requirement: Explicit Refresh reads current discovery
Explicit hub or speaker-library Refresh SHALL request fresh discovery within bounded client deadlines before using the resulting speaker observations. Identity and ambiguity checks SHALL remain enforced. Unavailable reads SHALL display errors; responses from older requests, speakers, or views SHALL NOT replace the current view.

#### Scenario: Cached speaker has no verified identity
- **WHEN** the user explicitly refreshes and discovery obtains its hardware identity
- **THEN** the subsequent overview read uses the newly discovered record and verifies its identity normally

#### Scenario: Discovery fails or the speaker changes while reading
- **WHEN** rediscovery fails, a read times out, or the user switches speakers
- **THEN** the UI reports the failure or rejects the obsolete result without device writes or automatic control retries
