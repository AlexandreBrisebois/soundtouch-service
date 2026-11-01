# Calm, dependable Wisp

Wisp keeps speakers and routines central: gentle wakeups and dependable audio,
with technology in the background. Existing speaker status, playback controls,
Turn All Off, schedules and the six physical button readout remain available.

## Phone navigation

The dock has **Speakers** and **Music**. Speakers retains its current controls;
**Refresh Speakers** and **Turn All Off** are actions above the dock. Refresh
rediscovers speakers and reads schedules/status, accepting an existing valid
15-second status snapshot. It does not search or browse NAS libraries.

Music offers global **Radio** and shared **Music Libraries**. Choosing a library
does not assign it to a speaker or start playback. A ready speaker provides the
native browse context; the speaker for Play, Schedule or Assign is chosen and
verified separately. A library visible on one speaker can still be unavailable
or not registered on another. See [library lifecycle](music-libraries.md).

## Inspect first, then choose an action

Tap a folder or playlist row to inspect its contents. Tracks show information
only in this version. The current collection name and path stay visible; Back
restores the previously loaded pages and scroll position. Load more appends
without jumping. Failed reads retain existing content and offer Retry; Empty
means a successful contents read with no items. A playable playlist whose
contents cannot be previewed says **Preview unavailable**, while retaining its
supported actions. Ordering remains controlled by the server/speaker; Wisp does
not edit playlists or add a shuffle mode.

The collection-labelled **Play / Schedule / Assign** area above the dock is an
accepted layout trial. Content space is reserved so the last row and Load more
remain reachable. Synthetic viewport checks can establish geometry; actual
phone thumb reach and visual review remain separate qualification.

- **Play** verifies the chosen speaker can access the inspected collection,
  explains replacement of current audio, and uses existing volume/playback
  safeguards. The same screen distinguishes accepted/starting, reported
  **Playing on room**, and failures, with session-bound **Stop**. Failures keep
  the collection and speaker for an explicit retry or another choice; Wisp does
  not switch speakers automatically.
- **Schedule** verifies access and opens the existing editor with the collection,
  library and speaker selected. **Change music** preserves the unsaved days,
  times, volume and fades, including when canceled. Saving does not play audio
  or assign a button. Direct collection schedules survive browser-token expiry
  and do not depend on any physical button. See [collection schedules](collection-schedules.md).
- **Assign** verifies preset capability and reuses the speaker's current six
  numbered slots. Review names the collection, library, speaker, button and old
  content. Final confirmation says **Assign** or **Replace Button N**. Cancel
  restores browsing. Assignment does not play; Play is a separate action.

Unsupported actions explain the missing capability. Actual playlist browsing,
playback, scheduling and physical preset support qualify separately; a folder
fixture or accepted command is not evidence of playlist or audible success.

## Recovery versus review pauses

A temporary NAS outage retains the added library as Unavailable. Startup and
Check Again reread observations; Ready returns only when observed. An ordinary
routine skips an unavailable due ON occurrence with a reason, without changing
source or volume, pausing/deleting the routine, falling back to another source,
or starting late. It checks normally at the next occurrence. Missing
registration requires explicit **Add Again**; Wisp never silently registers.

Explicit library removal pauses confirmed affected schedules while preserving
their settings and offering **Replace music**. Replacing a button warns and
pauses its affected button-based schedules before the write; direct collection
schedules are unaffected. Uncertain replacement outcomes retain those pauses.
Automatic library recovery does not clear a review pause. Review the selected
music and speaker, then explicitly re-enable the routine. A newer pause cannot
be cleared by a stale review form.

Native mutation timeouts are Unknown until readback. Check Again performs reads;
Wisp does not blindly retry a write. Remove deletes no music files, overwrites
no buttons, and warns that firmware may propagate registration changes.

## Global Radio

Existing stations remain available globally and directly in the routine editor.
Radio Play and Schedule are separate. Normal Play retains explicit chosen
listening volume and exact-session Stop; Test remains separate at volume 5.
Reported Playing and HTTP acceptance do not establish audible sound.

**Add Station** asks for name and direct HTTP(S) URL only. Choose the test
speaker, press **Test**, listen and acknowledge the intended sound, then **Stop**.
Save stays blocked until the test is confirmed stopped and audible sound is
acknowledged. URL edits require a new test; failures keep the fields visible.
Unknown Test/Stop outcomes offer a read-only status check before another request.
Existing stations are not retroactively forced through draft testing.

Experimental direct diagnostics retain their separate risk consent and bounded
behavior. They are not a fallback for automatic collection schedules, a proof of
quiet start, or a claim of physical-button support.
