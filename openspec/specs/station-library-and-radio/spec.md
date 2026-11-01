# Station library and radio Specification

## Purpose

Define the local station catalog and the native or Wisp-hosted radio paths that support manual and scheduled audio without consuming a physical preset.

## Requirements

### Requirement: Maintain a local station library
Wisp SHALL store named canonical HTTP(S) direct-stream URLs globally, separately from presets. It SHALL reject credentials, query strings, fragments, invalid schemes, duplicate active URLs and bounded-store violations. Listing SHALL require no speaker. New drafts SHALL require deliberate testing and user confirmation of audible sound on a chosen speaker before Save; saving SHALL not consume a preset.

#### Scenario: Station is saved
- **WHEN** a valid unique name and direct-stream URL have completed the draft test and audible confirmation
- **THEN** Wisp stores the station globally without starting new playback or changing a speaker preset

#### Scenario: Station is removed
- **WHEN** removal is explicitly confirmed
- **THEN** Wisp hides it while retaining private metadata needed by existing schedules, favorites or playback without stopping audio or clearing a button

#### Scenario: Existing stations are opened
- **WHEN** the user opens Radio or the existing radio schedule selector
- **THEN** existing and newly saved global stations are available without selecting a NAS library or re-testing existing records

### Requirement: Seed starter stations once without overwriting user state
On the first station-library read for a store without the seed marker, Wisp SHALL import non-conflicting entries from `app/data/stations.seed.json` and persist seed version 1. Existing active or archived names/URLs SHALL win, and an unwritable or full store SHALL remain unchanged and unmarked so initialization can be retried.

#### Scenario: Existing library is upgraded
- **WHEN** the seed marker is absent but user stations or favorites exist
- **THEN** Wisp adds only non-conflicting seed stations and preserves all existing IDs and records

### Requirement: Prefer native radio before gated relay playback
Wisp SHALL require a speaker-reachable `WISP_BASE_URL` and select native mode when the speaker has READY `LOCAL_INTERNET_RADIO` and `/select`, without applying relay URL eligibility. Only otherwise SHALL it evaluate the saved URL and origin for relay. Relay SHALL gate audio until volume zero, bind a bounded session to the intended speaker peer, and fade only after matching playback evidence.

#### Scenario: Native radio is ready for a non-relay URL
- **WHEN** the speaker reports READY `LOCAL_INTERNET_RADIO` and `/select` while the saved URL is not supported by the relay
- **THEN** readiness selects native mode and does not reject the URL for relay incompatibility

#### Scenario: Relay prerequisites are missing
- **WHEN** native radio is unavailable and the base URL is absent or unsafe, the source has no supported relay adapter, or the target cannot use the relay
- **THEN** readiness explains the failure and no stream or speaker command is started

#### Scenario: Manual station playback is confirmed
- **WHEN** the user confirms playback, readiness succeeds, and the operation is accepted
- **THEN** Wisp uses target volume 5 and the standard ownership/cancellation guards without writing a physical preset

### Requirement: Bound and revoke relay resources
Wisp SHALL limit concurrent radio sessions and consumers, revoke prepared/upstream streams on cancellation, takeover, EOF, shutdown, or failure, and SHALL not let an old cleanup or OFF operation close a replacement owner.

#### Scenario: Speaker or user takes over
- **WHEN** current playback no longer matches the owned relay session
- **THEN** Wisp closes the owned feed without sending a stale stop command to the replacement content

### Requirement: Restrict experimental direct radio tests
The direct UPnP radio path SHALL be available only as an explicit ten-second diagnostic for recognized candidate URLs, with separate confirmation of the remembered-volume risk. It SHALL NOT be used by automatic schedules or advertised as supporting physical presets.

#### Scenario: Direct test lacks risk consent
- **WHEN** the request omits either playback confirmation or startup-volume-risk acceptance
- **THEN** Wisp rejects it before selecting content or canceling an operation

### Requirement: Support the exact ICI HLS adapter when available
Wisp SHALL support only the exact configured ICI Première provider URL through the dedicated HLS adapter. The adapter SHALL be automatically available on Linux when FFmpeg is present, unless `WISP_ENABLE_HLS_RADIO=0` explicitly disables it, and SHALL permit at most two concurrent converters. Each converter SHALL accept only Wisp-fetched piped media input and SHALL be bounded and cancelable; availability SHALL NOT claim speaker or audible-playback qualification.

#### Scenario: ICI adapter prerequisites are absent
- **WHEN** the runtime is not Linux, FFmpeg is absent, or `WISP_ENABLE_HLS_RADIO=0`
- **THEN** readiness reports a concrete remedy and no fallback network input is passed to FFmpeg

#### Scenario: ICI converter capacity is exhausted
- **WHEN** two converters are already holding their bounded slots
- **THEN** a third conversion is refused without spawning another transcoder

### Requirement: Preserve exact relay-only station compatibility
Wisp SHALL apply a provider-verified relay alias only when the saved URL exactly matches its declared legacy URL. It SHALL keep relay aliases separate from direct speaker diagnostics and SHALL NOT persist resolved hosts or tokens, rewrite existing station records, or match edited variants.

#### Scenario: Existing CHOM station uses the verified relay source
- **WHEN** relay readiness or preparation receives the exact legacy seeded CHOM AAC URL
- **THEN** Wisp uses the stable CHOM HTTPS MP3 dispatcher through the existing gated MP3 relay while leaving the saved station unchanged

#### Scenario: New library receives the verified CHOM seed
- **WHEN** an unseeded station library imports starter stations
- **THEN** the CHOM starter entry uses the stable CHOM HTTPS MP3 dispatcher and the remaining starter stations retain their declared names and URLs

#### Scenario: Existing station state wins during seeding
- **WHEN** an existing, archived, deleted, renamed, favorited, or scheduled station conflicts with starter data
- **THEN** Wisp preserves its ID and persisted state rather than rewriting it to the current CHOM seed or relay alias

#### Scenario: Edited CHOM variant is not aliased
- **WHEN** a saved CHOM AAC URL differs from the declared legacy form by a query, fragment, case change, path change, or other edit
- **THEN** Wisp preserves that URL and evaluates it normally without applying the CHOM relay alias

#### Scenario: Direct diagnostics remain independently qualified
- **WHEN** direct speaker diagnostic availability is requested for the legacy CHOM AAC URL or the HTTPS CHOM MP3 dispatcher
- **THEN** Wisp does not advertise support unless that exact saved URL has a separately qualified direct HTTP candidate

#### Scenario: Relay transport evidence is not speaker qualification
- **WHEN** the aliased MP3 source passes offline transport and decode tests
- **THEN** Wisp continues to treat real-speaker delivery and audible playback as unverified

### Requirement: Test a station draft before saving
Add Station SHALL show name and URL fields without directory/search. Test SHALL explicitly choose a speaker, explain playback replacement and use existing safe test/playback and session-bound Stop semantics. Wisp SHALL keep fields visible, retain them on failure and require Stop completion before enabling Save after audible user confirmation.

#### Scenario: User completes an audible test
- **WHEN** matching playback is reported, the user confirms hearing the intended station, and the tested session is stopped
- **THEN** Save becomes available for that tested URL without claiming that reported playback alone proves sound

#### Scenario: User edits the URL or test fails
- **WHEN** the stream URL changes after testing, testing fails, or a Stop outcome is unknown
- **THEN** Wisp retains the form, clears stale test eligibility as appropriate, explains the failure and offers explicit retry/checking or another speaker without saving automatically

#### Scenario: Station is untested
- **WHEN** a new draft is submitted without a completed stopped test and audible confirmation
- **THEN** Wisp rejects Save with a field/action explanation rather than persisting an untested new station

### Requirement: Keep global radio Play and Schedule distinct
Radio Play SHALL select a target speaker and play immediately with explicit source/target and existing volume safeguards. Schedule SHALL open the existing editor separately with the station selected. Playback status and Stop SHALL remain on the initiating screen, and failures SHALL preserve station/target with Retry or other-speaker recovery.

#### Scenario: User plays an existing station
- **WHEN** Play is confirmed for the shown station, speaker and listening volume
- **THEN** Wisp reuses ordinary radio playback, shows accepted/starting and then Playing on the named room only after matching evidence, with session-bound Stop

#### Scenario: User schedules a newly saved station
- **WHEN** Schedule is chosen from global Radio
- **THEN** the existing editor offers that station directly alongside existing stations without a Music Libraries hop, new preset or playback action

## Evidence

- Implementation: `app/core/favorites.py`, `app/core/radio_relay.py`, `app/core/relay_playback.py`, `app/core/radio_upstream.py`, `app/core/radio_hls.py`, `app/core/direct_radio.py`
- Contract tests: `tests/test_favorites.py`, `tests/test_radio_relay.py`, `tests/test_radio_upstream.py`, `tests/test_radio_hls.py`, `tests/test_direct_radio.py`
- Qualification limits: `docs/native-presets.md`, `docs/direct-radio-tests.md`

