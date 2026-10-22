# Design

## Context

See `proposal.md` for motivation and `specs/station-library-and-radio/spec.md` for the behavior contract. The existing relay accepts general public HTTP/HTTPS URLs ending in `.mp3`, while the direct speaker diagnostic uses a separate explicit map of HTTPS saved URLs to qualified HTTP candidates. CHOM's current seed is an exact AAC URL, and existing seeded stores must remain immutable.

## Goals / Non-Goals

**Goals:**

- Resolve only the exact legacy CHOM AAC seed to the verified stable CHOM HTTPS MP3 dispatcher at the relay boundary.
- Make fresh station-library seeds use the MP3 dispatcher without changing seed version or existing persisted records.
- Retain all upstream validation and relay safety behavior after URL selection.

**Non-Goals:**

- Adding general AAC/HLS conversion, fuzzy URL matching, provider discovery, or persisted redirect resolution.
- Expanding the direct UPnP diagnostic allowlist or claiming speaker/audible compatibility.
- Migrating favorites, schedules, station IDs, archived/deleted records, or edited URLs.

## Decisions

### Keep the alias in relay URL selection

Add named legacy and MP3 URL constants beside `radio_relay.stream_url()` and return the MP3 constant only for exact equality with the legacy constant. This keeps the compatibility rule on the Wisp-hosted relay path, after native-radio precedence but before the existing upstream opens.

Adding CHOM to `radio_stream.CANDIDATES` was rejected because that map also advertises direct HTTP-only speaker diagnostics; the verified HTTPS MP3 relay source is not evidence of direct speaker support. General AAC conversion was rejected as unnecessary for the verified MP3 alternative.

### Seed the verified MP3 URL without a migration

Change only CHOM's URL in `stations.seed.json` and retain seed version 1. The existing seed-once and conflict rules mean fresh stores receive the MP3 URL while populated, archived, deleted, renamed, favorited, and scheduled records remain untouched. Bumping the seed version or rewriting stored entries was rejected because either could reintroduce a user-deleted choice or change stable IDs and links.

### Test selection boundaries, not provider availability

Unit tests will assert the exact alias, exact MP3 pass-through, edited/query variant preservation, unchanged direct-diagnostic candidates, unchanged non-CHOM seed entries, and existing seed preservation. Network probe evidence remains separate from deterministic tests; no test contacts speakers or starts playback.

## Risks / Trade-offs

- [The provider removes or changes the stable dispatcher] → The existing TLS, public-destination, content-type, and MP3-frame checks fail closed; update the exact constant only after new provider evidence.
- [The alias accidentally broadens through normalization] → Use literal string equality and regression tests for query, case, and path variants.
- [Seed editing affects existing users] → Keep seed version unchanged and test that populated and archived records win unchanged.
- [Relay support is mistaken for direct speaker support] → Leave the shared direct candidate map untouched and assert direct capability remains false.

## Migration Plan

Deploy without a data migration. Existing exact legacy CHOM records gain relay compatibility dynamically; new stores receive the MP3 seed. Rollback removes the exact alias and restores the prior seed value, with no persisted records to unwind. Real-speaker delivery and audible playback still require separate supervised qualification.
