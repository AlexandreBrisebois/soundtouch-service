## Why
Existing native presets are hidden behind assignment controls, configured services are filtered out, and explicit Refresh reuses incomplete discovery identities.

## What Changes
- Show native speaker slots separately from Wisp favorites and sanitized service availability.
- Explicit Refresh performs bounded rediscovery and reports errors without accepting stale speaker responses.
- Keep NAS browsing, identity checks, ambiguity checks, and all device controls unchanged.

## Capabilities
### Modified Capabilities
- `web-interface-and-api`: native speaker overview and explicit refresh behavior.

## Impact
Changes the local UI, discovery GET failure response, and additive favorites overview metadata. No changes to ownership, volume, physical presets, scheduling, or source registration. Offline regression evidence does not qualify real-speaker playback or audibility.
