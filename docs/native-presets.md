# Native presets and scheduled favorites (draft qualification)

Save a speaker-visible NAS folder or playlist on one of the speaker's six physical
buttons, then select that saved favorite in a routine. Radio uses Wisp's separate
Play and Schedule actions and is never assigned to a new physical preset. This is
a local-only feature. It does not register music accounts, mount NAS shares,
change DNS/firmware, or introduce multiroom playback.

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

Wisp-initiated radio uses native selection when the speaker exposes a ready source
and otherwise uses the guarded per-speaker relay. A stable speaker-reachable
`WISP_BASE_URL` is required for relay playback. Native and container development
startup infer `http://<LAN-IP>:9001` only when one private host address is available;
otherwise set the value explicitly. It is never inferred from an incoming Host
header. Startup selection is not proof that the speaker can reach the address.

New radio-to-button assignments are not supported. The preset-plan API rejects a
station ID, radio URL, or non-NAS browse item before creating durable intent or
sending a speaker write. Existing physical presets and legacy radio favorites are
not cleared, rewritten, migrated, or automatically recalled. Their read-only
descriptor route remains available so an existing speaker assignment can refetch
metadata.

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

Select a speaker and **Play…**, choose your listening volume, then press
**Play radio**. Wisp prefills the current volume only after a fresh verified
speaker read. If that read is unavailable, choose a volume explicitly. Normal
Play uses native radio selection or the guarded relay, with the existing identity,
volume-zero, source and ownership checks. It never writes a physical preset and
has no diagnostic listening timer. Keep Wisp running for relay playback.

After acceptance, Wisp opens the selected speaker page and shows accepted,
starting, reported playing, or a concrete failure. **Stop radio** stops only that
exact current listening session; an older Stop cannot stop replacement content
or another speaker, and Stop never toggles power. The separate **Test playback…**
action retains quiet volume 5 and any experimental direct-test risk consent.
Hardware audibility and provider compatibility still require supervised checks;
an accepted request or reported Playing state does not prove sound.

**Remove** removes the station from the visible library only. It never clears a
speaker button, rewrites schedules or stops audio. Its metadata remains privately
archived because a currently playing speaker may refetch it. New Play
requests for that removed ID are rejected. Existing legacy physical favorite
descriptors and schedules retain their own copy and continue unchanged. The confirmation
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

`app/data/stations.seed.json` is bundled initial data, not a third user-managed
configuration file. `CONFIG_FILE` (default `config.json`, `.wisp-dev.json` for
`task up`) stores schedules. `FAVORITES_FILE` defaults to `favorites.json` beside
`CONFIG_FILE`; it stores the station library and native preset favorite records,
not audio. Persist both runtime files across container replacement.

On the first station-library listing, Wisp imports the five seed suggestions once,
including into an existing empty library on upgrade: CHOM 97.7, Énergie Montréal
94.3, CBC **Radio One** Montréal (not CBC Music), ICI Première
Montréal 95.1 and Star 92.9. No import button, speaker selection or `WISP_BASE_URL`
is needed. Playback still requires normal radio setup and an explicit test.

The additions and `station_seed_version: 1` marker are saved atomically in
`favorites.json`. Existing exact URLs or trimmed, case-insensitive names win,
including archived/deleted records. Custom entries, IDs, favorites and schedules
are preserved. Restarts, reads and later removals do not apply the seed again.
Do not delete the runtime file or its marker to reset the library: that removes
the record that seeding already happened. A full or unwritable store reports an
warning without replacing existing data or marking the seed applied. Existing
records remain readable, removable and usable for playback; resolve the storage
problem and refresh the library to retry initialization.

The bundled URLs are starting points, not hardware-qualified sources. AAC/MP3,
HTTPS redirects and CBC/ICI HLS playlists may not work on every SoundTouch
firmware. A successful HTTP response is not proof of speaker compatibility or
sound, and seeding does not mark stations ready or fetch their streams. Playback
and scheduling remain separate, explicit actions. Broadcasters
may change URLs; manually add a replacement rather than silently rewriting saved
sources. Editing the bundled seed does not change a previously seeded library.
