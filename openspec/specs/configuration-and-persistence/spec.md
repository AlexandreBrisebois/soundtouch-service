# Configuration and persistence Specification

## Purpose

Define durable schedule and favorite state while preserving single-file Docker bindings and failing safely when state cannot be read or written.

## Requirements

### Requirement: Store schedules in a versioned document
Wisp SHALL persist schedules as a version 1 document containing a `schedules` map. It SHALL read the legacy root-level map, sanitize valid entries, and rewrite that legacy form to the versioned document without discarding supported fields.

#### Scenario: Legacy schedule file loads
- **WHEN** `config.json` contains a root-level speaker-to-schedules map
- **THEN** Wisp normalizes supported schedules, writes version 1, and uses the migrated data in memory

#### Scenario: Invalid entries are present
- **WHEN** individual speakers or schedules are malformed
- **THEN** Wisp logs structured warnings, skips invalid entries, and retains other valid schedules

### Requirement: Preserve a bind-mounted schedule file inode
The schedule writer SHALL serialize mutations through one worker and SHALL truncate, rewrite, flush, and fsync the existing `CONFIG_FILE` rather than atomically replacing its inode.

#### Scenario: Schedule changes inside a container
- **WHEN** `config.json` is mounted as a single host file
- **THEN** the write remains visible through that same mount and the in-memory configuration updates only after persistence succeeds

### Requirement: Persist favorites and stations atomically
Wisp SHALL store preset plans, favorites, station records, archived station metadata, and seed state in `FAVORITES_FILE`, defaulting beside `CONFIG_FILE`. It SHALL cap saved records, cap storage size, use atomic replacement, and block mutations when the file is corrupt or unwritable rather than erasing known state.

#### Scenario: Favorite store cannot be parsed
- **WHEN** the persisted document is corrupt
- **THEN** Wisp refuses programming and library mutations instead of replacing the file with an empty store

#### Scenario: Container persists favorites
- **WHEN** the deployment mounts a writable state directory and sets `FAVORITES_FILE` within it
- **THEN** atomic replacement remains inside the persistent directory

### Requirement: Keep transient operation state in memory only
Playback ownership, active fades, operation outcomes, and short-lived preset plans SHALL not be replayed after restart.

#### Scenario: Service restarts during an operation
- **WHEN** Wisp starts again
- **THEN** it reloads schedules and durable favorite intent but resumes no command, fade, or ownership lease

## Evidence

- Implementation: `app/scheduler/jobs.py`, `app/core/favorites.py`, `app/core/playback.py`
- Contract tests: `tests/test_scheduler_jobs.py`, `tests/test_favorites.py`, `tests/test_lifecycle_shutdown.py`

