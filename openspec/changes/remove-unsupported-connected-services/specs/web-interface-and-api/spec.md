# Spec Delta

## MODIFIED Requirements

### Requirement: Show speaker-native library observations
The speaker overview SHALL display native preset slots separately from Wisp favorites and SHALL display registered NAS music libraries that Wisp supports browsing. It SHALL identify speaker-reported Spotify as externally initiated Spotify Connect, omit unsupported cloud services, and preserve Wisp's independent internet-radio workflows.

#### Scenario: Speaker has presets and Spotify but no Wisp favorites
- **WHEN** the overview is loaded for a speaker with native presets, registered NAS libraries, and speaker-reported services such as Alexa, Amazon Music, or Spotify
- **THEN** native slots, the empty Wisp favorites state, and supported NAS libraries are presented in their separate workflows
- **AND** Spotify is presented as Spotify Connect with instructions to start playback from the Spotify app
- **AND** Alexa, Amazon Music, and other unsupported cloud-service availability are not included in the overview response or displayed in Settings
- **AND** no speaker command, account operation, or playback attempt is made

#### Scenario: Speaker has native presets but no Wisp favorites
- **WHEN** the overview is loaded without saved Wisp favorites
- **THEN** native speaker-button assignments remain visible beside the empty Wisp favorites state
- **AND** NAS browsing retains its existing identity, availability, and privacy checks

#### Scenario: Internet radio remains a Wisp workflow
- **WHEN** unsupported cloud-service summaries are omitted from the speaker overview
- **THEN** the Radio library and its existing Play, quiet Test, direct diagnostic, scheduling, relay-ownership, and recovery workflows remain available under their existing safety contracts
- **AND** Spotify Connect is not presented as a Wisp radio station or Wisp-controlled playback action
