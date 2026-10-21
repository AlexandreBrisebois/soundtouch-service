# Native presets and scheduled favorites (draft qualification)

Save a speaker-visible NAS folder/playlist or a compatible internet radio station
on one of the speaker's six physical buttons, then select that saved favorite in a
routine. This is a local-only feature. It does not register music accounts, mount
NAS shares, change DNS/firmware, or introduce multiroom playback.

## Before changing a button

1. Open **Presets & favorites** for the intended speaker. Record its current six
   buttons. Existing NAS buttons do not need to be rewritten merely to keep using
   existing routines.
2. Browse a NAS source already registered and READY on that speaker. Wisp offers
   only folders/playlists that the speaker marks playable and preset-capable.
   It preserves opaque source-account and location values. A filesystem path or
   arbitrary DLNA ID is not interchangeable with a SoundTouch content location.
3. Choose a name and button. Review the existing assignment in the preview.
   Cancel leaves the speaker unchanged. Confirm is an explicit physical-button
   write; any current Wisp automation fade is canceled first. It does not start
   music. The other five buttons must be unchanged in fresh readback.
4. A matched readback is not proof of sound. Use the explicit quiet test (volume
   5), then press the actual physical button. Test a short routine separately.
   A timeout or ambiguous readback is **unknown**, never success. Inspect before
   trying again; Wisp will not blindly retry or restore speaker presets.
5. In a routine, choose the saved favorite. It pins the speaker ID, button and
   intended content. If the source disappears or another app changes that button,
   Wisp does not play the replacement content. Existing unbound preset routines
   keep their old behavior. Scheduled OFF still stops whatever is playing.

Preview/browse selections expire after 15 minutes or a restart. Refresh and choose
again. A competing edit on any button invalidates a preview. Identical content
already assigned to another button is refused because some firmware moves it and
clears the original slot. New successful assignments supersede earlier Wisp
favorites on that button; existing schedules referencing them will stop safely
rather than silently follow the replacement.

## Radio readiness and limitations

Wisp serves a small, read-only Orion-compatible metadata document for each radio
favorite. The speaker fetches that document, then fetches the stream directly.
Wisp does not proxy, transcode, fetch, redirect or rewrite audio URLs. A stable
speaker-reachable origin must be explicitly configured as WISP_BASE_URL, e.g.
http://wisp.lan:9001. It is never inferred from an incoming Host header. Changing
that origin invalidates saved radio locations; old routines fail closed.

The form is enabled only when the speaker reports a READY LOCAL_INTERNET_RADIO
source and native /storePreset support. This is a prerequisite, not a guarantee.
Unmigrated firmware may still require unavailable cloud registration/token state.
Wisp does not create that state or deploy a companion server. If readiness fails,
existing presets remain usable and unchanged. Do not reset working buttons to
try to make the form appear.

Use a direct HTTP(S) audio stream, not a station website. Credentials, query
strings/tokens and fragments are refused; these can expose secrets and cannot be
safely treated as permanent station identities. This deliberately excludes some
providers. Local/private stream hosts and nonstandard ports require an explicit
operator allowlist WISP_RADIO_ALLOWED_HOSTS (comma-separated hostnames). This is
not a network security boundary: Wisp is a trusted LAN service, and the speaker
performs DNS resolution and stream fetching. Do not expose Wisp to the internet.
The metadata endpoint is unauthenticated so the speaker can read it; its opaque
favorite ID is not a credential or privacy guarantee.

## Persistence and deployment

Favorites live in FAVORITES_FILE, default favorites.json beside CONFIG_FILE.
Persist the containing directory, not just a single file bind mount: atomic
replacement needs a writable directory. A deployment example adds a separate
./state directory with FAVORITES_FILE=/workspace/state/favorites.json; it leaves
existing config.json binding unchanged. Back up both files together. They contain
speaker IDs and opaque NAS locations; keep them private. Wisp writes a durable
unknown intent before contacting the speaker. A crash never replays a write.
A corrupt/unwritable file blocks programming rather than discarding prior data.
The supported writer model is one Wisp process, matching the existing scheduler.
There is no automatic pruning or bulk rewrite. This first version caps saved
records at 500 and requires operator maintenance if that limit is reached.

## Protocol evidence, not hardware qualification

Source-inspected evidence:
- Native NAS navigation, selection and physical preset reports:
  https://github.com/gesellix/Bose-SoundTouch/issues/700
- AfterTouch protocol implementation and absolute Orion-location behavior:
  https://github.com/bosefirmware/AfterTouch/tree/075b6539e9b21ffc647afc621b1290efb6d2254e

The implementation preserves source/account/location. NAS now-playing may omit
`type=dir`; its absence alone is not a content mismatch. Another account or
location always is. Browse parsing reads the item's direct ContentItem, never a
nested mediaItemContainer parent. NAS queue order/shuffle/resume behavior remains
speaker-owned: Wisp does not expand tracks or promise a first-track restart.

Outstanding before release: user speaker model/firmware and NAS service; fresh
browse; explicit overwrite of an approved disposable button; physical recall;
quiet test; real ON/OFF routine; restart; NAS outage; station outage; radio source
readiness on unmigrated firmware; whole-map collateral readback. No installation,
speaker command, NAS configuration or audible test was performed during this
implementation. Browser visual qualification also remains outstanding.

## Test-first contracts

Automated fixtures cover XML shape and escaping, bounded/no-retry transport,
source/account identity, duplicate and incomplete preset maps, stale/expired
plans, write-ahead persistence, ambiguity, collateral changes, schedule pins,
quiet playback guards, safe metadata, URL restrictions and UI stale responses.
These are contract tests, not evidence that a particular firmware will work.
Keep issues #15 and #16 open until the qualification above is completed.
