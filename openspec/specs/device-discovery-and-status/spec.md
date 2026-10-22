# Device discovery and status Specification

## Purpose

Define how Wisp finds SoundTouch speakers, binds work to stable identities, and exposes current status without choosing an ambiguous or stale endpoint.

## Requirements

### Requirement: Discover speakers on the local network
Wisp SHALL discover SoundTouch speakers through `_soundtouch._tcp.local.` mDNS and cache each speaker's display name, IPv4 address, and `/info` device ID. When `WISP_SPEAKER_IPS` is set, Wisp SHALL instead accept at most eight unique RFC1918 IPv4 addresses and SHALL read each configured endpoint's name and device ID.

#### Scenario: Background discovery refresh
- **WHEN** the service starts or the five-minute refresh interval elapses
- **THEN** Wisp performs a bounded discovery scan, atomically replaces the cached snapshot, and updates WebSocket listeners for the new snapshot

#### Scenario: Invalid configured endpoint
- **WHEN** `WISP_SPEAKER_IPS` contains a hostname, public address, or more than eight addresses
- **THEN** Wisp rejects the configuration rather than probing the target

### Requirement: Resolve identity without guessing
Wisp SHALL treat a supplied device ID as authoritative across rename or DHCP address changes and SHALL NOT fall back to a same-name speaker when that ID is missing. Name-only resolution SHALL fail closed for duplicate names, and ID resolution SHALL fail closed when one ID appears at multiple addresses.

#### Scenario: Pinned speaker changes address
- **WHEN** a pinned device ID is present at one newly discovered address
- **THEN** Wisp resolves the operation to that address regardless of its current display name

#### Scenario: Discovery is ambiguous
- **WHEN** multiple endpoints have the same unpinned name or the same device ID appears at multiple addresses
- **THEN** Wisp returns no control target while retaining all records in the discovery listing

### Requirement: Provide bounded current status
Wisp SHALL expose status for a uniquely resolved speaker from a fresh-enough WebSocket cache when available and SHALL otherwise perform bounded `/now_playing` and `/volume` reads. Status SHALL distinguish Standby, Playing, Paused, Buffering, Stopped, unknown states, and offline reads.

#### Scenario: WebSocket state is available
- **WHEN** a current listener has cached speaker state within its freshness window
- **THEN** the status API returns that state without an additional polling read

#### Scenario: Cache is not ready
- **WHEN** no current cached state exists for a resolved speaker
- **THEN** the status API attempts fresh HTTP reads and reports unavailable evidence as offline or unknown rather than inferring playback

### Requirement: Keep private speaker identity data internal
Public status and operation responses SHALL omit opaque content location, source-account, and internal content-identity fields used to verify playback.

#### Scenario: Speaker reports opaque NAS metadata
- **WHEN** the speaker status contains a source account or content location
- **THEN** Wisp may use it internally for matching but does not return it in the public status or operation payload

## Evidence

- Implementation: `app/core/discovery.py`, `app/core/speaker_cache.py`, `app/core/status.py`, `app/api/routes.py`
- Contract tests: `tests/test_discovery_identity.py`, `tests/test_speaker_cache.py`, `tests/test_status_parsing.py`, `tests/test_api.py`

