# Experimental direct radio tests

This is a **supervised diagnostic**, not quiet playback, an automatic schedule,
continuous radio support, or physical speaker-button programming. Existing NAS,
native radio and routine behavior is unchanged. There is no automatic fallback.

## What is known

On a SoundTouch 10 with firmware 27.0.6, Star 92.9 played audibly using an HTTP MP3
URL via UPnP. A ten-second test then went silent after one Stop request. Bose
reported `INVALID_SOURCE` with no play status while UPnP reported
`PAUSED_PLAYBACK`. That is observed inactive after an acknowledged Stop, **not**
a verified UPnP `STOPPED` state. `TrackURI` identifies the audio; `CurrentURI` can
be a `qplay` wrapper and is not suitable as the ownership key.

Selecting a URI can start audio immediately at remembered volume, observed as
10 even when volume 5 or 0 was set beforehand. Ten is not a maximum. Therefore
this path cannot promise a quiet start and is never used by automatic schedules.

## Explicit manual test API

Read the station-specific warning and candidate availability:

`GET /api/<speaker>/stations/<station_id>/direct-test`

Only after the person has accepted the displayed warning:

`POST /api/<speaker>/stations/<station_id>/direct-test`

```json
{"confirmed": true, "accept_startup_volume_risk": true}
```

Keep physical Stop within reach. Stop other controllers/routines first. The
speaker must be idle, ungrouped, unmuted, with stable actual/target volume at most
30. This initial limit does **not** cap firmware's remembered startup volume.
The test validates the candidate, observes the speaker, selects once, then sets
and verifies volume 5. It observes for ten seconds and attempts one guarded Stop.
Closing the browser or stopping Wisp does not guarantee direct audio will stop.

The response gives an operation tracked by the existing
`GET /api/<speaker>/operations` endpoint. `physical_stop_may_be_needed` remains
true after selection unless the final stop readback is recognized. No audibility
claim is made. On ambiguous commands, changed source/volume/group, lost identity,
or supersession, no further commands are sent. Use the physical controls if the
speaker is still playing. Volume is never restored automatically.

The known candidates are exact original saved seed URLs, or their exact HTTP
MP3 equivalents: Star 92.9, The Buzz, and CBC Radio One Montreal (CBME-FM).
Public HTTP responses/audio bytes were checked for all three; only Star has been
heard on the user's hardware. A user-edited station URL is not replaced with a
guessed station. The resolved session URL is temporary and never saved. CHOM,
Énergie, and ICI Première are not enabled by this diagnostic.

Each redirect must remain ordinary HTTP on port 80 and resolve only to public
addresses. Requests connect to a validated literal IP with the original Host
header, avoiding a second DNS resolution; environment proxies are not used.
The probe samples at most 512 audio bytes, six hops, with a 15-second wall budget,
socket shutdown deadline and bounded DNS workers. It does not relay or record
radio. The speaker's later connection is outside Wisp's HTTP transport: providers
may change URLs or return different data to the speaker. This remains a manual
compatibility test, not a guarantee about future station behavior.

## Different stations on different speakers

These direct tests use the existing per-device playback ownership and write
locks. Each speaker fetches its own stream. Starting or canceling a test on one
device does not stop a test on another. A replacement operation on the same
speaker invalidates the old operation: its later volume or Stop must not act on
the new station. Names resolving to the same device share ownership. No zones
are created or dissolved.

The Wisp relay uses a separate opaque stream-session URL per device and
operation, independent upstream connection, cancellation token and bounded
buffer. Stopping one session closes only its upstream/downstream resources. Two
speakers, including two playing the same station, have independent consumers.
All audio bytes remain gated until both actual and target volume are verified
for the current owner. Sustained and multi-speaker relay operation still require
supervised hardware qualification.

## Physical buttons: still a separate hardware gate

Native `LOCAL_INTERNET_RADIO` preset programming retains its existing readiness
checks and explicit preview/confirm/readback flow. This direct test does not
create that source or prove that UPNP items can be stored as native presets.

Primary-project evidence points instead to an always-on marker bridge:

- [SoundTouchBridge](https://github.com/codingmammoth/SoundTouchBridge) reports on
  ST20 that a native `source="UPNP"` preset can wedge the renderer until reboot.
  It uses native descriptor markers, WebSocket selection events and UPNP playback.
- [soundtouch-radio-bridge behavior notes](https://github.com/dani6282/soundtouch-radio-bridge/blob/main/docs/soundtouch-behavior.md)
  describe distinct AUX markers and `nowSelectionUpdated` intent. Generic
  activity/now-playing events must not start audio. AUX is not intrinsically
  silent if a cable/source is connected, so it is not an unconditional safe marker.
- [bose-soundtouch](https://github.com/fredgaiotti/bose-soundtouch) reports UPNP
  playback on ST10 firmware 27.0.6. Its force-invalid and group-reset behavior is
  not adopted: Wisp must preserve users' other sources and independent speakers.

Before any physical-button implementation is enabled, obtain an explicitly
chosen disposable slot and snapshot all six assignments, show old/new preview,
confirm the write, verify whole-map readback, and capture real ST10 selection
XML. Preserve a recoverable previous assignment. All six user slots are occupied;
none may be silently replaced. A marker bridge must require Wisp running, use
only an explicitly mapped identity/slot/marker, ignore stale/reconnected events,
and respect manual standby/volume/source changes. No marker write, background
listener playback, registration or rollback is enabled by this change.

## Scheduled radio: a separate, volume-gated path

Schedules do **not** use the supervised direct diagnostic or its remembered-volume
risk acceptance. If a ready native `LOCAL_INTERNET_RADIO` source exists, the
existing native selection path remains in use. Otherwise eligible stations use a
Wisp-hosted, per-speaker MP3 stream:

1. Validate/open the upstream before changing the speaker. Public HTTP and HTTPS
   MP3 are accepted; HTTPS verifies certificates and refuses downgrade redirects.
2. Give the idle speaker a random, speaker-IP-bound Wisp stream URL. Selection can
   auto-play and reset volume to 10, but Wisp sends headers and **no audio bytes**.
3. Verify current TrackURI, device, solo zone, actual **and target** volume zero,
   and unmuted state. Only then release audio; verify reported playback at zero
   before the configured fade to the requested volume.
4. Keep the stream lease until that routine's OFF, explicit local override,
   disconnect, failure, or shutdown. A stale routine's OFF cannot stop a later
   routine or station. OFF fades to zero and sends one guarded Stop; the observed
   `INVALID_SOURCE`/paused transition is “acknowledged inactive”, not verified
   `STOPPED`. No volume restoration or source rollback is attempted.

Every speaker has its own upstream, token, volume gate and lifetime—even when two
speakers select the same station. Stopping one does not stop another. Eight MP3
sessions are allowed per process; ICI conversion has an additional two-converter
limit. An automatic ON encountering an active Wisp radio lease leaves it alone.
Quiet manual tests require an idle speaker; stop current audio first.

After an exact current relay has reached speaker-reported Playing, a speaker
client disconnect may reserve one short-lived recovery attempt for that same
in-memory operation. Recovery first requires fresh matching device identity,
saved station URL, prior Wisp TrackURI/UPNP source, solo zone, and original
actual/target volume. It then confirms both volume values at zero **before**
selecting a new peer-bound relay URI, and keeps audio gated until the intended
speaker connects at zero. A second disconnect is not retried. Stop/OFF,
replacement, manual control, takeover, expiry, shutdown, and process restart
invalidate recovery; no grant is persisted or resumed.

This is AVTransport recovery qualified by tests and, separately, supervised
speaker observations. The official Bose Web API reference does not specify URI
repush or lost-stream reconnection, and reported Playing does not prove audible
sound. Wisp never uses POWER for relay recovery, never restores volume after
ambiguous evidence, and does not expose a generic SoundTouch control proxy.

Set `WISP_BASE_URL=http://<container-host-LAN-address>:9001` to the stable address
reachable **from the speakers**, not localhost or a browser-only hostname. Wisp
must stay running. The relay uses the existing threaded Werkzeug container server
and its socket cancellation support; other WSGI servers without that support are
refused. Upstream startup/read and downstream write timeouts, fixed worker/session
caps and socket shutdown bound resources. This is a single-process service; a
multi-worker deployment would need a shared lease/routing design.

The readiness endpoint performs no station fetch. Enabled schedule saves validate
configuration and format eligibility; actual stream framing and access are checked
at startup before speaker selection. A paused draft may be saved while unavailable.
Provider 403 responses remain access failures: a relay cannot bypass them.

Known exact Star/Buzz/CBC seed URLs have explicit MP3 equivalents; edited/custom
`.mp3` URLs are used exactly, never silently replaced with another station. ICI's
exact seed URL has an optional, narrow Linux/FFmpeg adapter described in
[ICI relay](ici-radio.md). Other HLS/AAC formats are not assumed compatible.

The earlier speaker experiment demonstrated audio gating and the Stop transition.
The production Flask streaming route, long scheduled sessions, multi-speaker use,
and ICI conversion still need a supervised hardware check. Automated tests mock
all device/network traffic and are **not** proof of audible playback. Physical
radio buttons/preset programming remain deferred and unchanged.

### Repeated routines and restart boundary

An automatic radio start normally requires Standby. A successful, owned relay OFF
can grant **one** later automatic radio attempt from its exact no-source/paused
state on that same device. The attempt rechecks fresh identity, Bose `INVALID_SOURCE` with empty play status,
AVTransport `PAUSED_PLAYBACK`/`OK`, solo zone and unchanged actual/target volume.
This is not general permission to start from `Unknown`. Failed/skipped attempts,
local overrides, changed playback/volume observations and process restart lose the
permission. Native/preset automatic startup keeps its existing Standby rule.
After a container restart, put an unselected speaker into Standby before its next
routine. An explicit quiet station test remains available, but does not itself
restore automatic idle permission; stop playback and put the speaker into Standby
before the next routine. Never infer ownership from stale transport fields. No
schedule is resumed automatically after restart.
