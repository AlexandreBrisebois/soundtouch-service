# Design

## Context

See proposal.md for motivation. `stations.js` currently maps both Play and Test playback to a volume-5 confirmation and `/play`; `jobs.queue_station` fixes the target to 5. Production relay playback is continuous and volume-gated. `direct_radio.run` alone adds the diagnostic ten-second stop. The speaker page has a POWER action, not a radio session Stop.

## Goals / Non-Goals

Provide normal volume selection and session-specific Stop using existing production control. Preserve library refresh work, schedules, presets and all ownership guards. No live tests, automatic wake, discovery redesign, persistence migration or runtime startup.

## Decisions

- Add a read-only listening-options endpoint that verifies identity, obtains readiness and reads live volume. Do not prefill from the cached status API. Missing volume is nullable and never implicitly becomes 5.
- Normal `/play` requires explicit volume and pinned speaker identity. Give the existing quiet test a separate `/test` endpoint that calls the same production engine at 5; leave the experimental `/direct-test` contract unchanged. This separates intent without duplicating audio transport.
- Extend the station queue to carry the chosen volume and expose station, speaker identity and listening-session metadata in outcomes. Retain the two-second safe fade and existing zero-volume gate.
- Reuse a pending station operation only when station, speaker identity, volume and listening/test intent match. Reject conflicting pending requests with HTTP 409 before cancellation; a pending quiet test must not silently satisfy an everyday listening request.
- Stop accepts the displayed operation ID, station and speaker identity. Under the playback lock it rejects stale owners, then transfers only the matching playing radio ownership. Relay stop reuses the verified relay stop path; native stop uses source-guarded STOP with inactive readback, never the generic power-based OFF path. A queued old stop cannot act after replacement.
- Keep the speaker detail's existing outcome polling. Add a dedicated Stop radio control only for a current playing listening operation. Capture its identifiers before awaiting; a late response cannot overwrite another speaker or newer operation.
- Distinguish missing discovery ID, failed live `/info` verification and identity mismatch. Do not repair timeouts by loosening checks.

## Risks / Trade-offs

- A manually changed source makes Stop unsafe: refuse further commands on mismatched content.
- Old callers that omit listening volume now receive an actionable validation error; the explicit quiet test endpoint retains volume-5 behavior.
- Volume may change while the form is open: chosen volume remains an explicit user decision; the worker revalidates actual preflight state and still gates startup at zero.
- Accepted commands cannot prove sound: retain separate reported-state and hardware/audibility evidence.

## Migration Plan

Implement and test offline, obtain review, then use a separately agreed restart window. No stored data conversion is needed. Rollback is code-only. Hardware qualification remains unchecked.
