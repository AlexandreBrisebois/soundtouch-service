# Archive record

Archived on 2026-11-01 at the user's explicit request to sync and archive the
implemented change, with the known qualification work still incomplete.

Implementation commit: `09adda4f70e74593459e04e09ace35390b0e05f3`.

## Pending qualification stays open

The [tracked task list](tasks.md) remains **21/24 complete**. These entries remain
unchecked and are deferred, not passed or waived:

- **7.3:** approved native hardware discovery/Add/Remove, timeout readback,
  restart/outage and registration propagation qualification.
- **7.4:** real folder/playlist playback and direct scheduling, approved physical
  assignment/recall and audible confirmation.
- **7.5:** physical-phone visual/thumb-reach review of the accepted trial layout.

Archival does not authorize device actions, production testing or completion of
these checks. Retain this archive's task IDs when recording future evidence.

## Evidence and scope

The [implementation verification record](implementation-status.md) retains the
software evidence: 962 Linux tests passed with one optional FFmpeg integration
skip, 914 Windows-portable tests passed, and lint/types/JavaScript/spec checks
passed. Those are historical execution results, not newly rerun hardware tests.
Earlier planning/implementation statements in this archive describe those phases;
this record identifies the later sync/archive operation.

All five selected deltas were synced to canonical capabilities. Other active
changes and canonical content outside those deltas were left untouched. The
original tasks and implementation evidence are preserved without marking any
additional task complete. Sync/archive changes are local and uncommitted.

## Final sync/archive validation

All nine canonical specs passed strict noninteractive validation, and this change
passed strict validation before archival. After archival, aggregate validation
reported **12 passed, 1 failed**: the separate active `use-wisp-radio-playback`
change has stale MODIFIED blocks that omit newly canonical scenarios:

- NAS/presets: User reviews an assignment; Replacing a scheduled button.
- Scheduling: Old configuration is loaded.
- Web/API: User navigates Music.

That older change requires a deliberate rebase preserving today's contracts before
it can be safely synced/archived. It was audited read-only and left untouched;
no requirement or validation check was weakened to hide the conflict. This archive
is complete, but aggregate validation is not currently green for all active changes.
