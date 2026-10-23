# Spec Delta

## ADDED Requirements

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
