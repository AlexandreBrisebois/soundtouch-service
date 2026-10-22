# Proposal

## Why

Radio relay playback requires a speaker-reachable `WISP_BASE_URL`, but native `task up` currently starts without one and the container task requires operators to discover and export it manually. A safe shared startup resolver should preserve explicit configuration while making the ordinary local path work when exactly one private LAN address is available.

## What Changes

- Validate and honor an explicit `WISP_BASE_URL` for both native and container startup.
- When no override is supplied, derive `http://<private-lan-ip>:9001` only when host interface inspection yields one unambiguous private IPv4 address.
- Fail before starting Wisp when no usable private address or multiple candidates exist, with an actionable `WISP_BASE_URL=http://YOUR_LAN_IP:9001` instruction.
- Keep localhost, link-local, public, credentialed, or malformed origins ineligible for the speaker callback URL. Treat an explicit RFC1918 address as the operator's selection without claiming speaker reachability.
- Do not alter radio playback ownership, volume gates, peer binding, schedules, physical presets, or speaker configuration.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-and-deployment`: Make supported local native and test-container startup establish a validated speaker-reachable callback origin or stop with an actionable error.

## Impact

- Startup tooling: `task up`, `task container:up`, and their shared URL validation/resolution helper.
- Tests: explicit override, automatic single-interface resolution, ambiguous/no-interface refusal, and unchanged checkout/container safety boundaries.
- Documentation: local and container startup no longer require manual URL export on an unambiguous LAN, while explicit configuration remains the deterministic fallback.
- Speaker behavior: none during startup validation; offline tests do not establish real-speaker relay reachability or audible playback.
