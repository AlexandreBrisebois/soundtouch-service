# Proposal

## Why

The speaker overview currently advertises Alexa, Amazon Music, Spotify, and other speaker-reported sources uniformly as “Ready,” even though their post-cloud behavior differs. Bose's [SoundTouch end-of-life notice](https://www.bose.com/soundtouch-end-of-life) says its cloud support ended on May 6, 2026, in-app music-service browsing and playback no longer work, and Alexa voice commands no longer work; Spotify Connect remains available as an external Spotify-app workflow. The current Settings label obscures that distinction and can also be misread as applying to Wisp's independently implemented internet radio.

## What Changes

- Replace the generic Connected services section with an External playback presentation that identifies speaker-reported Spotify as Spotify Connect and directs the user to start it from the Spotify app.
- Stop including Alexa, Amazon Music, and other unsupported cloud-service summaries in the speaker overview API response or Settings.
- Replace the generic `services` response with an allowlisted external-playback summary; initially, only speaker-reported Spotify maps to Spotify Connect.
- Continue showing physical speaker-button assignments, Wisp favorites, and NAS music libraries registered on the selected speaker.
- Preserve Wisp's independent internet-radio library, normal Play, quiet Test, direct diagnostic, scheduled playback, relay ownership, and bounded stalled-relay recovery behavior.
- Preserve refresh, identity, stale-response, and privacy protections for the remaining speaker-library observations.
- Do not add service playback, account management, or a full SoundTouch API implementation; Bose's published local API is used selectively only where Wisp has an owned, tested workflow.

This display/API correction does not change speaker ownership, volume safety, physical preset programming, Wisp radio playback, or scheduling. The Bose notice does not state that direct internet-radio streams are unavailable, and it does not govern Wisp's locally relayed radio path. Bose separately warns that cloud-era preset access is no longer supported or guaranteed; reconciling Wisp's existing local preset workflow with that statement is outside this focused change and requires its own evidence-led review. This change requires no speaker command and no real-speaker or audibility qualification; offline API and browser-contract evidence is sufficient.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-interface-and-api`: Distinguish Spotify Connect as external playback, omit unsupported cloud-service availability, and preserve Wisp-supported radio, library, and preset workflows.

## Impact

- Affected UI: `app/templates/index.html` and `app/static/presets.js`.
- Affected API composition: `app/core/favorites.py` and its overview response contract.
- Affected documentation: `docs/reference/README.md` will record the Bose end-of-life source and the Wisp-radio distinction.
- Affected tests: focused speaker-overview API, preset UI, and radio-surface regression coverage.
- No new dependencies, persistence changes, network discovery changes, device writes, speaker restarts, or hardware operations.
