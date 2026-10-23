# Proposal

## Why

A Wisp-owned relay can end while a SoundTouch speaker continues to report the old UPNP URI and `PLAY_STATE` even though it is silent. Wisp currently reports the disconnect honestly but leaves the listener with no safe automatic recovery path, while the Bose Web API reference defines observable source, playback, volume, and STOP surfaces without promising stream liveness or reconnection.

## What Changes

- Preserve a short-lived, in-memory recovery grant only after an exact Wisp-owned relay that had reached reported Playing ends with `radio_client_disconnected`.
- Attempt one automatic recovery for the same logical manual or scheduled operation only after fresh matching speaker identity, prior relay URI, station URL, ownership, grouping, and actual/target volume evidence.
- Create a new gated relay lease and token, confirm volume zero before selecting the replacement URI, and restore the selected target volume only after the intended speaker reconnects and reports matching playback.
- Invalidate recovery on Stop/OFF, cancellation, replacement, takeover, changed content or volume, shutdown, expiry, worker unavailability, or any ambiguous read/write. Never loop, retry an ambiguous command, toggle POWER, restore an unsafe volume, or affect another speaker.
- Expose pending, recovered, declined, and failed recovery outcomes without treating protocol state as audible confirmation. An exact Stop or scheduled OFF while recovery is pending cancels recovery without sending a stale speaker command.
- Document that the official SoundTouch Web API supports the observation and STOP/volume surfaces used by Wisp but does not specify AVTransport stream recovery; keep real-speaker and audibility qualification separate.
- Do not change physical presets, saved station/configuration data, native-radio behavior, direct diagnostics, or the two active changes' pending hardware tasks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `station-library-and-radio`: Add one-shot, volume-gated recovery for an exact disconnected Wisp relay and define all invalidation boundaries.
- `playback-safety-and-ownership`: Preserve logical ownership only through a bounded recovery state and make Stop/OFF, replacement, takeover, and shutdown atomically win over recovery.
- `web-interface-and-api`: Report recovery progress and outcomes honestly while allowing the exact session Stop action to cancel pending recovery without claiming a speaker command was sent.

## Impact

Touches volatile playback outcomes, relay lease lifecycle, station worker dispatch, operation APIs/UI status, focused documentation, and offline race/contract tests. Recovery reuses existing per-speaker serialization, fresh device reads, guarded volume-zero sequencing, peer-bound relay consumers, and STOP-only session control. No persistence migration or new dependency is planned. Offline evidence can establish ordering and isolation; firmware reconnection, speaker-reported state, and audible recovery still require separately authorized supervised tests, one speaker and one action at a time.
