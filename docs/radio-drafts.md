# Add Station: Test, Stop, then Save

Radio is a global station library. Existing stations remain available to Play
and to the existing schedule selector without re-testing or opening Music Libraries.

Add Station asks for a name and a direct HTTP(S) stream URL. It has no directory
or search. Choose the intended speaker and explicitly Test: this replaces that
speaker's current audio using the existing guarded radio path at quiet volume 5.
The name and URL stay visible, including when the request fails.

Reported Playing means matching speaker evidence, not proof of sound. Confirm
that you heard the intended station. Stop that exact test session, wait for a
verified stopped result, then Save. Saving adds the station globally without
starting audio or assigning a speaker button. Changing the stream URL requires a
new test; changing only its name does not.

If Stop is unknown, check again before saving. A stale Stop cannot stop a newer
session. Test does not switch to another speaker automatically. Keep Wisp running
while testing: drafts and test evidence are transient and disappear on restart.
No station is saved before the completed test. Draft descriptors are retained for
the process lifetime so live speakers can refetch them; a bounded full draft store
reports an error instead of evicting potentially active sessions.

Software checks can verify this lifecycle and your acknowledgement, but actual
sound and firmware compatibility still need supervised qualification.

If a Test outcome is uncertain, Check first. Wisp can recover an exact native
session when fresh speaker evidence matches it, so Stop can safely proceed. If
an unknown test cannot be recovered, put the speaker in standby with its normal
controls, then Check. Fresh verified standby permits a deliberate Retry, but
does not count as a successful audible test or enable Save. No Check sends a
playback command or silently switches speakers.

Saved stations also keep a separate quiet Test at volume 5. Its same-screen Stop
is bound to that exact test session, just like normal listening Stop; it does not
convert Test into normal chosen-volume playback or permit an old Stop to affect a
replacement session. Experimental direct diagnostics keep their separate risk
consent and diagnostic limits.
