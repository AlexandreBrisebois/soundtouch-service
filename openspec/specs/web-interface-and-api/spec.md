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
The UI SHALL expose Speakers and Music navigation, with Radio and Music Libraries under Music. Play, Schedule, Assign, Test and Remove SHALL remain distinct deliberate actions. Saving SHALL not imply playback; assignment SHALL require preview/confirmation. Existing speaker controls, routines, immediate NAS playback and six-slot content readout SHALL remain available.

#### Scenario: User saves a station
- **WHEN** the tested station form succeeds
- **THEN** the UI reports that no new playback or preset changed and refreshes global Radio

#### Scenario: User navigates Music
- **WHEN** the phone dock opens Music
- **THEN** Radio and Music Libraries are clear destinations and choosing a library does not require choosing the eventual Play/Schedule/Assign speaker first

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

### Requirement: Show speaker-native library observations
The speaker overview SHALL display native preset slots separately from Wisp favorites, even when there are no Wisp favorites. It SHALL show sanitized service availability without raw account identifiers or account display names. Service summaries SHALL be informational and SHALL NOT enable non-NAS browsing or imply working playback.

#### Scenario: Speaker has presets and Spotify but no Wisp favorites
- **WHEN** the overview is loaded
- **THEN** native slots and Spotify availability are visible separately from the empty Wisp favorites list
- **AND** account identifiers remain private and NAS browsing retains its existing checks

### Requirement: Explicit Refresh reads current discovery
Explicit Refresh Speakers SHALL request fresh speaker discovery and schedule/status observations within bounded deadlines. A valid existing 15-second status snapshot SHALL be acceptable. It SHALL not discover or rescan NAS libraries. Library refresh/check actions SHALL be explicit and separate. Identity checks and stale-response rejection SHALL remain enforced.

#### Scenario: Cached speaker has no verified identity
- **WHEN** explicit refresh obtains its hardware identity
- **THEN** subsequent observations use that discovered record and verify identity normally

#### Scenario: Discovery fails or the speaker changes while reading
- **WHEN** rediscovery fails, a read times out or the user switches speaker/view
- **THEN** the UI reports failure or rejects obsolete results without device writes or automatic control retries

#### Scenario: Home is refreshed
- **WHEN** Refresh Speakers is selected on Speakers
- **THEN** Wisp refreshes speaker discovery, schedules and status using the normal snapshot rules without sending media-server discovery, NAS browse or registration writes

### Requirement: Keep home actions above the phone dock
Speakers SHALL retain working status, playback, controls and schedules. Refresh Speakers and Turn All Off SHALL remain labelled content actions above the Speakers / Music dock, not navigation destinations. Dock and action areas SHALL reserve content space and support phone touch and keyboard use without covering controls or rows.

#### Scenario: Home controls are used
- **WHEN** a user views Speakers on a phone
- **THEN** status, schedules and existing playback/controls remain accessible, with Refresh Speakers and Turn All Off above the two-destination dock

### Requirement: Preserve collection inspection position
The browser SHALL show current collection name and path, full-width content targets and distinguish loading, empty, failed with Retry, and Preview unavailable. Back SHALL restore loaded pages and scroll; Load more SHALL append without jumping. Leaving an action by Cancel SHALL restore the inspected collection and position.

#### Scenario: User returns from nested browsing
- **WHEN** Back returns to a parent with multiple loaded pages
- **THEN** the prior pages and scroll position return without a new action or unwanted jump

#### Scenario: More content is loaded
- **WHEN** Load more succeeds or fails
- **THEN** existing rows and scroll position remain; success appends rows and failure offers Retry without pretending the collection is empty

#### Scenario: Empty and failed differ
- **WHEN** a valid enumerable collection has zero items or its contents read fails
- **THEN** Wisp respectively shows Empty or a concrete failure with Retry, using Preview unavailable only for the accepted unpreviewable-playlist case

### Requirement: Trial collection actions above the dock
The inspected collection SHALL have a text-labelled Play / Schedule / Assign action area above the phone dock, labelled with the current collection. It SHALL reserve space so the last row remains reachable and explain unsupported actions. Its phone layout SHALL remain a trial until later visual/thumb-reach qualification; this plan SHALL not claim such qualification.

#### Scenario: User reaches the last row
- **WHEN** a long folder/playlist is inspected on a narrow phone viewport
- **THEN** the last row and Load more remain reachable above reserved action/dock space without overlays intercepting them

#### Scenario: User chooses an action
- **WHEN** Play, Schedule or Assign is selected
- **THEN** target speaker choice appears if needed, source accessibility is verified and the corresponding distinct workflow opens with current collection context

### Requirement: Explain recovery and review pauses to users
User documentation and visible outcomes SHALL explain temporary-outage skips and automatic observation recovery, explicit Add Again for missing registration, and persistent review pauses caused by removal/button replacement. They SHALL distinguish accepted work, reported Playing, native readback and audible/physical qualification.

#### Scenario: User investigates a skipped or paused routine
- **WHEN** its source is unavailable or requires review
- **THEN** the reason and Check Again, Add Again or Replace music/re-enable path are explained without implying automatic registration, fallback audio or automatic clearing of a review pause

## Evidence

- Implementation: `app/templates/index.html`, `app/static/stations.js`, `app/static/presets.js`, `app/static/sw.js`, `app/api/routes.py`, `app/api/favorites.py`, `app/main.py`
- Contract tests: `tests/test_playback_ui.py`, `tests/test_stations_ui.py`, `tests/test_presets_ui.py`, `tests/test_routes_validation.py`

