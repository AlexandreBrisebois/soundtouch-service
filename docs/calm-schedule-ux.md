# Calm, schedule-first Wisp

## Direction

The README sets the purpose: a sanctuary at home, gentle wakeups and routines,
with technology in the background. The hub is devices; each device leads to its
schedules. Wisp is not becoming a general-purpose music player.

The everyday path is **speaker → schedule → what to play → when → save**.
Library management and speaker-button assignment are secondary, explicit actions;
a user does not need to understand six physical presets to choose a radio station.

- One `What to play` choice shows only its relevant fields: radio station,
  saved favorite, speaker button, or AUX. Switching choices preserves selections
  within the draft, but only the chosen source is submitted.
- New schedules ask for music rather than silently selecting button 1. Existing
  schedules reopen in their correct mode. The existing paired on/off model stays
  unchanged; this slice does not introduce stop-only schedules.
- A saved favorite may be NAS music or a radio assignment. Do not rename all
  favorites “NAS”; do not imply that saving a station assigns a physical button.
- Existing NAS browsing is labelled **Music connected to this speaker**. It reads
  the selected speaker's registered sources; it is not network-wide discovery.
  Browsing and playing already-working folders remain unchanged.
- Radio-library management and music-library / physical-button setup live in
  collapsed Settings sections, below devices or schedules. Native disclosure
  controls work with keyboard and do not fetch data or send speaker commands.
  An explicit assignment action opens its Settings section before confirmation.
- Keep the existing station primary Schedule action and accessible overflow menu.
  Test playback and physical button assignment belong in that menu, not beside
  every ordinary schedule field.

## Next cohesive steps (not implemented here)

Make the NAS browse flow start from a schedule with its speaker already chosen,
use folder breadcrumbs and one clear selection action, and return to the intact
unsaved schedule. Keep “Assign to speaker button” secondary. A future network
finder must distinguish “visible to this speaker” from “registered and ready”; it
must not silently register, retry uncertain registrations, or overwrite presets.

Surface playback confirmation/errors beside the action that initiated them.
The existing Test action checks station-specific readiness. Available native or
volume-gated relay playback uses the normal play path; relay tests explain that
the speaker must be idle and Wisp must remain running. If explicitly unavailable,
it can offer the backend's bounded experimental direct test for a
known candidate station. The offer is not a claim of hardware support. A separate,
initially unchecked checkbox acknowledges remembered startup-volume risk before
the direct-test POST. Changing speaker or leaving cancels stale capability reads
and clears consent. Unknown readiness fails closed. The schedule editor checks the selected station,
shows backend setup requirements without discarding the choice, and surfaces
station-specific save validation errors. Backend validation remains authoritative. Direct requests are never labelled quiet and are not retried.

Radio scheduling readiness is unchanged by this UI work. A successful manual
transport test is not evidence of native hardware preset support or reliable
scheduled playback. Do not advertise those capabilities until independently
verified. Multiple speakers must retain independent sessions and cleanup.

## Verification

Offline tests cover mode visibility, exclusive payloads, blank radio/favorite
validation, draft selection retention, existing schedule modes and new-speaker
reset. The existing station overflow keyboard and destructive-action tests still
run. No speaker, preset, or user configuration is changed by these tests.

Rendered browser and real speaker acceptance testing remain necessary before
calling the experience end-to-end verified.
