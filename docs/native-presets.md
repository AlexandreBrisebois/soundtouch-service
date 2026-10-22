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

## Stations: a library separate from six buttons

The Stations page saves names and canonical direct-stream URLs without requiring
an available speaker or consuming a physical button. Seven or more stations can
be saved (a bounded 500 records, separate from favorite records). No personal
station list is shipped or published. The storage remains local in favorites.json.

Select a speaker and **Play quietly** to start that station at volume 5. The
confirmation explains that current audio is replaced. Wisp verifies identity,
source readiness and /select capability, confirms volume zero, sends a direct
ContentItem selection, and only fades after fresh matching Playing. It never
writes a preset to play a station. After acceptance, the app opens the selected
speaker page for existing playback status and controls. Dedicated in-page
Stations now-playing/volume/stop controls are not part of this draft. Cancellation/manual-takeover protections are
the same as routine playback. Radio firmware/HTTPS/redirect support still needs
real-device qualification; accepted requests and descriptor responses are not
proof of sound. Wisp supplies the canonical URL unchanged; any stream redirects
are followed by the speaker, not validated or fetched by Wisp.

**Assign to preset** opens the existing explicit six-button preview/confirmation.
Assignment creates an independent immutable favorite copy of the station URL.
That favorite can be scheduled as before. The station library itself is not
limited to six buttons; simultaneous physical assignments still are.

**Remove** removes the station from the visible library only. It never clears a
speaker button, rewrites schedules or stops audio. Its metadata remains privately
archived because a currently playing speaker may refetch it. New Play/Assign
requests for that removed ID are rejected. Existing physical favorite descriptors
and schedules retain their own copy and continue unchanged. The confirmation
explains this distinction. This is not a secure erase or automatic retention
policy; archived records count toward the bounded storage limit. A hard purge
would require a separate explicit decision after checking device references.

**Schedule** selects a saved station directly in the existing routine editor.
Choose the speaker, days, ON/OFF times, volume and fades. No physical button is
required or consumed, even for the seventh station. The routine persists station
and speaker IDs; scheduled ON uses the same direct selection but stays polite
when the speaker is already active. OFF retains its existing stop-whatever-plays
behavior. Existing preset, NAS-favorite and AUX routines remain unchanged.

A routine may select either a saved station or a preset favorite, not both.
Removing a station from the library keeps already configured routines working
through the archived station record. Those routines can still be edited without
losing the binding; archived stations cannot be attached to a new routine. A
same-name replacement speaker cannot silently inherit a previously pinned
routine. Existing runtime timezone/restart semantics remain those of #18.


### Starter stations

**Stations → Add starter stations** (`POST /api/stations/starter` with a JSON
object) adds six public stream suggestions: CHOM 97.7, Énergie Montréal 94.3,
CBC **Radio One** Montréal (not CBC Music), The Buzz 99.9, ICI Première Montréal
95.1 and Star 92.9. No speaker selection or `WISP_BASE_URL` is needed to save them.
Playback still requires the normal radio setup and an explicit listening test.

The import is deliberately optional rather than a startup seed: an empty library
and a user's deletions are valid choices. Opening Stations or restarting Wisp
never restores deleted stations. Clicking the action again can add removed
suggestions back as new records; archived playback links remain unchanged.
Repeated requests skip visible entries with the same exact URL or a matching
trimmed, case-insensitive name, retaining their names, URLs and IDs. Custom
entries, favorites and schedules are untouched. A custom URL under a starter's
name takes precedence. The whole batch is saved atomically; a storage error adds
none. The UI blocks repeat clicks while saving and never retries writes itself.

The bundled URLs are starting points, not hardware-qualified sources. AAC/MP3,
HTTPS redirects and CBC/ICI HLS playlists may not work on every SoundTouch
firmware. A successful HTTP response is not proof of speaker compatibility or
sound, and adding these entries does not mark them ready. Wisp does not fetch the
streams during import. Playback, button assignment and scheduling remain separate,
explicit actions. Broadcasters may change their URLs; manually add a replacement
when needed rather than silently rewriting a user's saved source.
