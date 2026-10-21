# Playback reliability contract (review implementation)

This is a conservative, per-speaker foundation for #17, not a hardware-readiness claim
or a radio/NAS integration. Physical buttons 1–6 and their existing assignments are
never programmed, overwritten, migrated or reset. A NAS/media server remains necessary
for presets that depend on it. No real speaker was contacted during implementation.

## Outcomes

Each run has an operation ID, schedule name, acceptance/update/observation timestamps,
reason, terminal flag and in-flight command flag. `accepted` means queued; `starting`
means checking/starting, not playing. Terminal states are:

- `playing`: fresh matching content and Playing reported by the speaker, plus confirmed
  final volume. This is **not proof of audible sound**.
- `completed`: scheduled OFF followed by fresh Standby readback.
- `skipped`: automatic ON found activity, or OFF found Standby.
- `unknown`: missing evidence, deadline, ambiguous identity or unconfirmed command/volume.
- `failed`: internal worker error.
- `canceled`: cancellation, supersession or detected manual takeover invalidated an active run.

A failed/ambiguous command is not retried. Terminal history is not rewritten by later
manual activity. Only the last operation per speaker is retained, in memory. Restart
clears outcomes, bindings, pending operations and fades; no operation resumes.

HTTP 202 and saved schedules do not establish playback. `/api/<speaker>/operations`
works without a reachable speaker; `/api/<speaker>/schedules/runtime` supplies next-run
and timezone metadata without changing the saved schedule response. The existing view
shows small indicators and cancellation, not a dashboard. No push notification, fallback
station or automatic replay is added. Raw ContentItem locations/accounts stay internal.

## Quiet start

1. Resolve and verify stable speaker identity; read fresh playback state. Automatic ON
   skips existing activity. Explicit Run Now can replace audio, even for a paused schedule.
   Unknown/unreachable state never authorizes a POWER toggle.
2. Read the existing preset's ContentItem (`/presets`, read only), or identify AUX.
   A preset needs source and opaque location; compare other returned identity fields too.
3. Set/read back volume zero **before** source selection. Stop on unconfirmed writes.
   Do not roll volume back: that could amplify an old/manually selected source. A failed
   start may leave the speaker quiet.
4. Send PRESET_n or AUX_INPUT directly, without POWER. Require fresh matching content
   and Playing before fading. Buffering, cached Playing and friendly names do not qualify.
5. Guard each fade write against fresh source/playback/volume changes; confirm volume
   rather than claiming a target was reached because HTTP succeeded.

There is no source whitelist. Offline fixtures cover realistic NAS STORED_MUSIC items,
including server/playlist locations. If a firmware returns a different child-track identity
from the selected folder/playlist, this conservative match ends unknown without fade-up.
AUX proves reported input/transport only, not audible input. Missing reliable identity
also ends unknown rather than guessing.

**Hardware compatibility change:** direct source keys replace POWER-then-select startup.
Firmware that cannot wake through PRESET/AUX, or cannot confirm zero volume in standby,
will end unknown. No blind POWER fallback is attempted. Qualification is required before
merging/deploying; this PR does not claim to fix unsupported firmware/source behavior.

## Identity, cancellation and manual priority

Discovery indexes stable device IDs independently of names/IPs. Duplicate names or an ID
at multiple addresses fail closed. An operation binds to an ID and resolves its current
address; every write verifies `/info` again. Legacy name-based config stays readable and
binds on first use **in this process**. There is no automatic durable migration: after a
restart, a unique same-name replacement can become the first match. Operators can supply
optional `speaker_id` on a schedule after verifying the device. Pins survive config writes,
edit and pause/resume. A missing bound ID never falls back to a name.

Playback and volume freshness are independent. Playback cache expires after 15 seconds;
new playback does not freshen an old volume. Reconnect primes again. Changed IP/identity
replaces listeners; obsolete callbacks and mismatched IDs cannot publish.

One operation owns a speaker. Concurrent repeated Run Now for the same pending schedule
coalesces; another run supersedes it. Manual power/preset/volume cancels automation before
waiting for its per-device command lock, then resolves/verifies the target inside the lock.
Cancel automation sends neither STOP nor POWER; existing audio can continue.

Cancellation and command reservation are atomic. After cancellation wins, no later command
can reserve. An already-reserved/in-flight bounded command can finish; the following manual
command waits for it. `in_flight` exposes that limit. No global lock spans network I/O.

WebSocket messages wake fresh reconciliation rather than trusting delayed own echoes.
Long waits recheck fresh playback/volume every five seconds between reads when no event
arrives, and each fade step checks before writing. A fresh mismatch ends the fade. There
is no speaker-side atomic ownership API: same-source/same-volume actions and changes
inside an in-flight command cannot always be distinguished. Physical-button interception
is not instantaneous or infallible; real-device race qualification remains necessary.

**Owner decision:** a newly due scheduled OFF preserves existing behavior and acts on
whatever is currently playing, including manually started audio. It is not limited to
Wisp-owned sessions. A manual change during an already-active fade cancels that fade and
remaining writes. OFF checks fresh identity, playback and volume before toggling.

## Budgets and schedules

- Reads default to 5 seconds; each volume write or complete press/release pair has a
  3-second budget. No implicit retries or redirects. Streamed XML is capped at 64 KiB.
  An already-blocked socket may exceed a deadline by up to its socket timeout.
- Start has a 30-second monotonic budget, including discovery/source readiness. Commands
  do not start after expiry. Discovery identity lookup waits up to 5 seconds collectively,
  with at most 64 endpoints and eight simultaneous reads.
- Fades are finite, at most one hour. Elapsed-time targets avoid adding request latency
  to every sleep. Duration plus 120 seconds bounds verification; slow devices end unknown
  rather than extend indefinitely. Exact audible timing is not promised.
- Server-local `TZ` owns scheduling, as before. Next-run timestamps include UTC offsets.
  Spring-forward gaps are skipped; a repeated fall-back wall minute fires at most once
  per local date/process. There is no catch-up scan for earlier missed minutes.
- Startup-minute behavior remains pending the owner's decision. No durable run ledger
  is added; current-minute startup semantics have not yet been changed.

## Qualification

Before hardware-readiness claims, separately authorize one-speaker, safe-volume testing:
record model/firmware, read existing preset mappings without changing them, verify source-key
wake, existing NAS presets and server dependencies, AUX, physical buttons, manual source/
volume/stop/power during fades, cancellation, partial/time-out responses, restart, DHCP,
reconnect and source outage. Record reported Playing separately from human listening.

Offline tests prohibit live HTTP/discovery/WebSocket construction by default. They cover
transport/XML failures, real-shaped identities, cache generations, identity ambiguity,
reservation/cancellation ordering, real waits under a fake clock, delayed event reconciliation,
schedules, API and Node-based UI behavior. Mock tests do not establish hardware compatibility.
