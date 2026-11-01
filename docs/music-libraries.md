# Music libraries: native registration and recovery

Music Libraries is shared across speakers. A library can be visible to several
speakers but registered or Ready on only some. Wisp asks speakers for their own
media-server discovery results; it does not mount your NAS or replace Bose/Marge.
Keep the NAS music/DLNA service enabled and allow the speaker on the same network.

**Add Library** shows discovered stable server identities and which speakers saw
them. Choose the library and intended speaker, then explicitly Add. Wisp shows
Adding and Checking availability. **Ready** means both registered and available
on that speaker. **Added, Unavailable** keeps the selection and offers **Check
Again**. Discovery alone does not add or play anything. Discovery choices and speaker visibility describe only
the latest scan; retained added libraries are listed separately even when that
scan finds no server. Search Again is safe if
no servers were found; failures are shown separately from an empty result.

A timeout does not mean that a command failed to reach the speaker. Wisp reads
registrations before offering an explicit retry. An **Unknown** outcome offers
checking; it never repeats a write automatically. An acknowledged command whose
result is not yet observed also stays in checking. When readback conclusively
shows that a change was not applied, an explicit Retry becomes available; removal
still requires a fresh impact review. Check Again itself sends no registration or
removal write. The speaker may report a native
credential or firmware error even with HTTP success. Wisp keeps the selection and
shows the error; there is no replacement service or hidden account repair.

## Remove a registration

Use the library's secondary Remove action, choose the speaker, and review known
schedule/button impacts. The warning explains that firmware may propagate removal
to other speakers and that offline speakers have unknown impacts. Confirm only the
reviewed removal. Cancel sends no command and pauses no routine. If impacts change
before confirmation, review a fresh plan.

Removal uses the speaker's exact registered source account. It deletes no music
files and does not clear or overwrite physical buttons, which may retain stale
references. Wisp rereads all known speakers. It keeps the shared library wherever
still registered and removes it from the added list only after observed absence
on all known speakers. Paused schedule references remain recoverable. A removed
library may be discovered and explicitly added later.

Confirmed source removals pause affected schedules with a reason; their other
settings remain intact. Choose Replace music, review and explicitly re-enable.
If a speaker was offline, Wisp retains pending reconciliation and pauses its
confirmed affected schedules when its observations return. A still-registered speaker
also retains a possible-propagation check: firmware can propagate later, so a first
present read is not final proof it was unaffected. No propagation timeout is assumed.
An explicit successful Add establishes a new registration generation; earlier
removal intents cannot pause that newer registration. A missing registration while
a prior removal remains unresolved conservatively requires review; ordinary
Registered unavailable outages do not. Reappearance or Add
Again does not automatically re-enable these review pauses.

## Temporary outages and restart

A temporary outage retains the library as Unavailable/Unknown; an unavailable read
is not evidence that registration was removed. Startup and Check Again reread
sources without adding anything. Ready returns when availability is observed.
Missing registration shows **Not registered** with explicit **Add Again**.

Temporary outages skip unavailable scheduled ON occurrences with a reason; they
do not pause/delete the routine, select a fallback, or start it late. The next
normal occurrence checks again. This automatic observation recovery differs from
explicit-removal or button-replacement review pauses, which require your review.

## Evidence limits

Offline fixtures verify native XML, bounded transport, stable-ID deduplication,
explicit writes, readback and recovery. They do not establish firmware support,
propagation behavior, working physical buttons or audible music. Those require
separately authorized supervised checks on the actual speakers and NAS. A native
acknowledgement or Ready observation is not an audible test.
