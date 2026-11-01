# Direct collection schedules

Choose an inspected NAS folder or playlist, then **Schedule** and the target speaker.
Wisp verifies that speaker can access the collection and opens the existing routine
editor with the collection/library/speaker selected. Times, weekdays, volume and fades
use the existing controls. Save does not play music or assign a physical button.
**Change music** replaces the source while preserving the other routine settings.

Collection routines save durable source intent, independent of browse-session expiry
and six physical buttons. Wisp rechecks the source on the pinned speaker when due.
Missing registration, unavailable NAS, ambiguous/missing content or changed speaker
identity skips that ON occurrence with a reason before source/volume writes. Wisp
never substitutes Button 1 or other audio, never catches up the missed occurrence,
and checks again at the next normal occurrence. Temporary outages do not pause or
delete a routine. Existing OFF timing and behavior are unchanged.

Explicit library removal or replacement of a scheduled physical button is different:
affected routines are retained but paused with a review reason. Recovery does not
clear that pause. Review the source, use **Replace music** if needed, and explicitly
re-enable the routine. A failed/uncertain button replacement can leave conservative
review pauses in place. This avoids routines following unconfirmed replacement audio.

Old station/favorite/AUX/button routines retain their semantics. New collection fields
survive normal persistence/reload and older-client edits; unsupported collection data
is reported unavailable rather than converted into a button routine. Back up schedule
and favorites/library state together before upgrading. Do not downgrade older code
against newly saved collection routines: older versions can drop unknown fields and
select a default preset. Disable those routines or restore pre-upgrade state first.

Isolated software checks are separate from real folder/playlist compatibility,
physical-button recall and audible sound. Those remain supervised qualification work.

If a removed library's prior favorite or button source identity cannot be verified,
Wisp labels that impact unknown and can conservatively pause that unresolved routine
on the affected speaker for review. Other known routine impacts are still processed;
an unavailable favorite does not hide them. The review reason identifies the missing
source identity. Re-enable only after checking or replacing the intended music.

When editing an existing collection routine, choosing a different speaker moves that
routine after the new speaker's collection access is verified. The original is removed
and the new target saved in one serialized configuration mutation; no second active
copy is left behind. A conflicting target routine name, changed original music/pause
revision, or unavailable target prevents the move and retains the original for review.
Other routine settings and any review pause remain intact. Moving a routine does not
move or stop an already running playback session, play music, or assign a button.
Replacing missing collection music with a saved radio station (or another existing
source mode) retains the same routine settings and review pause. If a new speaker is
chosen at the same time, Wisp verifies the final source on that target and performs
the same guarded single-routine move; it does not leave the old routine running on
its former schedule or silently overwrite another target routine.
