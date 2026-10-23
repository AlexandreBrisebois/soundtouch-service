# Runtime and deployment Specification

## Purpose

Define the self-hosted process, container, network, time, and lifecycle assumptions required for Wisp's device and scheduling behavior.

## Requirements

### Requirement: Start and stop background services with the application
Wisp SHALL start the bounded schedule/config worker pool, scheduler, device cache, and speaker WebSocket listeners as part of application creation. Registered shutdown SHALL stop listeners, discovery, relay/playback state, workers, and scheduler idempotently.

#### Scenario: Application exits
- **WHEN** the registered shutdown handler runs more than once or after partial startup
- **THEN** each background component is stopped safely without replaying or extending operations

### Requirement: Run as a local Flask service
Wisp SHALL bind the Flask service to `0.0.0.0` on `PORT`, defaulting to 9001, and SHALL keep the app self-hosted without requiring cloud credentials for its own state.

#### Scenario: No port override is provided
- **WHEN** the application module is launched directly
- **THEN** the hub and API listen on port 9001

### Requirement: Preserve LAN discovery and speaker reachability in Docker
The supported deployment SHALL use host networking for mDNS discovery, or operators SHALL provide explicit private speaker IPs where multicast is unavailable. The deployment SHALL set the intended `TZ`, persist `config.json`, and mount a writable directory for `favorites.json`.

#### Scenario: Synology deployment uses the supplied compose file
- **WHEN** the container starts with host networking and persistent mounts
- **THEN** Wisp can perform LAN discovery, schedule against the configured timezone, and retain schedules and favorites across replacement

### Requirement: Include the bounded radio conversion dependency
The Linux container image SHALL install the pinned FFmpeg package used by the exact ICI HLS adapter and SHALL run the Python application as `python -m app.main`.

#### Scenario: Container handles supported ICI HLS
- **WHEN** the exact adapter is selected in the bundled Linux image
- **THEN** FFmpeg receives only the bounded pipe input produced by Wisp rather than an arbitrary network URL

### Requirement: Keep local developer processes checkout-scoped
The local Taskfile SHALL refuse to start on an occupied port or existing run marker and SHALL stop only the recorded process after verifying its command, start identity, and working directory.

#### Scenario: Recorded PID was reused
- **WHEN** `task down` finds a process whose identity no longer matches the saved record
- **THEN** it refuses to signal that process and retains state for inspection

### Requirement: Isolate test-container and unit-test state
Container development SHALL use per-checkout names, ownership labels, and test state, and SHALL operate only on its owned containers through a local Docker engine. It SHALL preserve source schedules and favorites and retain test state on down. The isolated Python unit suite SHALL fail application networking through Requests, Zeroconf, WebSocketApp, HTTPConnection.connect, and DNS; it does not block every raw socket path or separately authorized manual probes.

#### Scenario: Test container is started for a checkout
- **WHEN** ownership, local-engine, port, path, and LAN settings checks pass
- **THEN** Wisp builds and starts the uniquely named and checkout-labeled container with only `.wisp-container` mounted, copying schedules paused and favorites only on first preparation without modifying their source files

#### Scenario: Test-container boundary is unsafe
- **WHEN** the engine is remote, container ownership is foreign or uncertain, an owned container already exists, or the state directory or files are symbolic links
- **THEN** Wisp refuses to build, replace, start, stop, or inspect beyond the safe ownership check

#### Scenario: Test container is stopped
- **WHEN** the named container has the checkout's expected ownership label
- **THEN** Wisp stops and removes that container by inspected ID while retaining `.wisp-container` for later runs

#### Scenario: Unit code attempts live network access
- **WHEN** an isolated pytest test reaches a patched Requests, Zeroconf, WebSocketApp, HTTP connection, or DNS boundary
- **THEN** the test fails at that boundary; raw sockets to literal IPs are not covered, and manual hardware diagnostics remain a separate explicit workflow

### Requirement: Establish a speaker-reachable radio callback origin at startup
Supported native and test-container startup SHALL honor a syntactically valid explicit RFC1918 `WISP_BASE_URL` as the operator's selection without claiming reachability. Without an override, startup SHALL use an HTTP origin on port 9001 only when local interface inspection finds exactly one eligible private IPv4 address after filtering known local-only interfaces. It SHALL fail before launching or replacing Wisp when automatic resolution is unsafe or ambiguous.

#### Scenario: Explicit private origin is supplied
- **WHEN** the operator starts native or container Wisp with a valid private-LAN `WISP_BASE_URL`
- **THEN** startup preserves that origin unchanged except for removing a trailing slash and does not claim that the speaker can reach it

#### Scenario: One eligible private address exists
- **WHEN** no override is supplied and local interface inspection returns exactly one private IPv4 address after excluding loopback and link-local addresses
- **THEN** startup sets `WISP_BASE_URL` to `http://<address>:9001` before launching Wisp

#### Scenario: Address selection is ambiguous or unavailable
- **WHEN** no override is supplied and interface inspection returns zero or multiple eligible private IPv4 addresses
- **THEN** startup does not launch, stop, rebuild, or replace Wisp and tells the operator to set `WISP_BASE_URL=http://YOUR_LAN_IP:9001`

#### Scenario: Explicit origin is unsafe
- **WHEN** the configured origin is localhost, link-local, public, credentialed, malformed, not HTTP, or not port 9001
- **THEN** startup rejects it before launching Wisp and explains the accepted private-LAN form

## Evidence

- Implementation: `app/main.py`, `Dockerfile`, `deployment/docker-compose.yml`, `Taskfile.yml`, `scripts/container_dev.py`
- Contract tests: `tests/test_lifecycle_shutdown.py`, `tests/test_container_tasks.py`, `tests/test_dependency_smoke.py`, `tests/test_docker_release.py`

