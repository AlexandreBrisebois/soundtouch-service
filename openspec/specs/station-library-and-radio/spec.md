# Station library and radio Specification

## Purpose

Define the local station catalog and the native or Wisp-hosted radio paths that support manual and scheduled audio without consuming a physical preset.

## Requirements

### Requirement: Maintain a local station library
Wisp SHALL store named canonical HTTP or HTTPS direct-stream URLs separately from speaker presets. It SHALL reject credentials, query strings, fragments, invalid schemes, duplicate active URLs, and bounded-store violations, and SHALL NOT require a speaker merely to add or list a station.

#### Scenario: Station is saved
- **WHEN** a valid unique name and direct-stream URL are submitted
- **THEN** Wisp stores the station without starting playback or changing a speaker preset

#### Scenario: Station is removed
- **WHEN** removal is explicitly confirmed
- **THEN** Wisp hides the station from the library while retaining private metadata needed by existing schedules, favorites, or playback, without stopping audio or clearing a button

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

## Evidence

- Implementation: `app/core/favorites.py`, `app/core/radio_relay.py`, `app/core/relay_playback.py`, `app/core/radio_upstream.py`, `app/core/radio_hls.py`, `app/core/direct_radio.py`
- Contract tests: `tests/test_favorites.py`, `tests/test_radio_relay.py`, `tests/test_radio_upstream.py`, `tests/test_radio_hls.py`, `tests/test_direct_radio.py`
- Qualification limits: `docs/native-presets.md`, `docs/direct-radio-tests.md`

