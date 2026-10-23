# Spec Delta

## ADDED Requirements

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
