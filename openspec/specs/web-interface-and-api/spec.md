# Web interface and API Specification

## Purpose

Define the local PWA and HTTP interface used to see speakers, manage routines, make deliberate manual changes, and access supporting station and preset workflows.

## Requirements

### Requirement: Present a speaker-first hub
The web interface SHALL fetch discovery and schedules concurrently, wait for both requests to settle, combine discovered and configured speaker names, render the resulting speaker cards, and then load per-speaker status lazily.

#### Scenario: Discovery is unavailable but schedules exist
- **WHEN** the concurrent hub requests settle with saved schedules available but live discovery unavailable
- **THEN** configured speaker names remain accessible with unavailable status

### Requirement: Present schedule controls and honest outcomes
The speaker detail view SHALL list routines, their pause state, next server-computed run, and the latest matching operation. It SHALL provide add/edit, pause/resume, Run Now, delete, cancel automation, power, and volume controls while distinguishing accepted work from confirmed playback.

#### Scenario: Run Now returns accepted
- **WHEN** the API accepts a manual schedule run
- **THEN** the UI shows the operation as queued/starting and refreshes outcome data rather than saying that audio is already playing

### Requirement: Keep supporting workflows separate and explicit
The UI SHALL expose station-library and native-preset workflows as separate views/actions. Saving a station SHALL not imply playback, assigning a preset SHALL require preview and confirmation, and play/remove/direct-test actions SHALL display their distinct confirmations and risks.

#### Scenario: User saves a station
- **WHEN** the station form succeeds
- **THEN** the UI reports that no playback or preset changed and refreshes the library

### Requirement: Validate API writes and avoid automatic retries
The HTTP API SHALL validate schedule, volume, favorite, station, and confirmation payloads before queuing device or persistence work. User-directed writes SHALL not be automatically repeated after network or ambiguous command failures.

#### Scenario: Speaker command acknowledgement is ambiguous
- **WHEN** a manual power, preset, or volume command cannot be confirmed
- **THEN** the API returns an unknown 502 outcome rather than success or an automatic retry

### Requirement: Serve local app and API documentation
Wisp SHALL serve the app shell with no-cache response headers, static PWA assets including a service worker, and generated API documentation at `/apidocs/`.

#### Scenario: Browser revisits the application
- **WHEN** the root app shell is requested
- **THEN** the response prevents stale HTML caching while static assets remain available through the service worker strategy

## Evidence

- Implementation: `app/templates/index.html`, `app/static/stations.js`, `app/static/presets.js`, `app/static/sw.js`, `app/api/routes.py`, `app/api/favorites.py`, `app/main.py`
- Contract tests: `tests/test_playback_ui.py`, `tests/test_stations_ui.py`, `tests/test_presets_ui.py`, `tests/test_routes_validation.py`

