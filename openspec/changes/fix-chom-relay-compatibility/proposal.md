# Proposal

## Why

The seeded CHOM URL is a valid AAC stream but the general MP3 relay cannot consume it, so existing and newly seeded CHOM entries fail relay readiness even though the provider exposes a stable, home-network-verified MP3 dispatcher. An exact relay-only compatibility mapping restores CHOM without broadening direct speaker diagnostics or silently rewriting user data.

## What Changes

- Map only the exact legacy seeded CHOM AAC URL to the exact stable HTTPS CHOM MP3 dispatcher when the Wisp relay prepares the upstream.
- Seed new station libraries with the stable CHOM MP3 dispatcher while retaining the alias for existing favorites and schedules.
- Preserve direct saved MP3 URLs exactly, including accepted query variants, and leave edited CHOM AAC variants unsupported rather than guessing.
- Keep the direct UPnP diagnostic candidate set unchanged so it does not advertise HTTPS-only CHOM support to speakers.
- Preserve volume-zero gating, ownership and cancellation behavior, public-address/TLS validation, native-radio precedence, station IDs, archived/deleted choices, favorites, schedules, and physical presets.
- Treat offline tests and silent stream decoding as transport evidence only; actual speaker fetch behavior and audible playback remain unqualified.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `station-library-and-radio`: Define exact relay-only CHOM compatibility for legacy saved stations and the new-install CHOM seed without changing direct diagnostics or existing user state.

## Impact

- Affects `app/core/radio_relay.py`, `app/data/stations.seed.json`, and focused radio/seed contract tests.
- Adds no dependency, API shape, converter, credential, background service, speaker command, or migration of persisted data.
- Manual and scheduled CHOM relay selection can use the existing MP3 relay; all existing safety and ownership gates continue to apply.
