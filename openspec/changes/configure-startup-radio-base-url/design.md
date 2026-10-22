# Design

## Context

See `proposal.md` for motivation and `specs/runtime-and-deployment/spec.md` for the startup contract. Native `task up` currently inherits no callback origin; the container runner validates only a mandatory explicit value. Both paths must agree without relying on an incoming HTTP Host header or changing the application radio safety model.

## Goals / Non-Goals

**Goals:**

- Use one small Python resolver for native and container startup.
- Preserve explicit operator intent after strict private-origin validation.
- Infer an origin only from bounded local interface information and only when the choice is unique.
- Resolve before any run marker, image build, container change, or application process launch.

**Non-Goals:**

- No network scan, route mutation, DNS change, or reachability claim.
- No application restart, schedule migration, speaker command, or playback change.
- No relaxation of relay peer binding or acceptance of localhost/public callback URLs. An explicit RFC1918 origin is operator-selected and syntactically validated, not probed or proven speaker-reachable.

## Decisions

### Share URL validation and address selection

A dependency-free helper will validate explicit origins, filter candidate IPv4 addresses, and return the canonical origin. The container runner will call it instead of maintaining a second validator, and the native task will invoke it before creating `.wisp-run`.

Keeping separate shell and Python validators was rejected because their acceptance rules could drift. Moving inference into request handling was rejected because startup configuration must be stable and must not trust client-controlled Host headers.

### Treat ambiguity as an operator decision

Automatic selection succeeds only for one distinct RFC1918 address. Zero or multiple candidates produce an actionable error. Explicit `WISP_BASE_URL` remains the supported way to select among Ethernet, Wi-Fi, VPN, or other private interfaces.

Selecting the default route was rejected because a VPN or Docker route can be the host default while remaining unreachable from the speaker. Probing speaker addresses was rejected because startup resolution must not contact devices.

### Inspect interfaces through bounded platform adapters

The helper will parse bounded outputs from the host's standard interface tools: `ifconfig` on macOS/BSD and `ip -json -4 addr show` on Linux. Automatic selection filters known loopback, Docker, bridge, and virtual Ethernet interfaces. Tests inject command output and do not inspect the developer host. Missing tools, malformed output, and command failures are treated as no trustworthy candidate.

Adding a networking package was rejected because this is a startup-only need and the existing environment can supply the required data without a new runtime dependency.

### Keep launch ownership behavior unchanged

The native Taskfile retains its port/run-marker/process-identity checks. Container state, ownership, paused first-copy schedules, peer binding, and Docker safety checks remain unchanged. URL resolution happens before mutating either startup path.

## Risks / Trade-offs

- [A machine has several legitimate private interfaces] → Refuse inference and require an explicit URL rather than guessing.
- [A unique private address is still unreachable by the speaker] → Describe inference as configuration, not reachability proof; retain supervised playback qualification.
- [Platform output changes] → Keep parsers bounded and fail closed with the explicit-override instruction.
- [Native and container startup diverge later] → Cover both callers against the shared resolver in focused tests.

## Migration Plan

1. Add resolver unit tests for explicit, inferred, ambiguous, absent, and invalid values.
2. Integrate the resolver into native and container startup before their first mutation.
3. Update startup documentation and run focused plus complete automated tests.
4. Do not restart an already-running instance automatically; the new origin takes effect on the next operator-controlled start.

Rollback restores mandatory manual configuration for the container and inherited-only configuration for native startup. No persisted schedules, favorites, presets, or speaker state require rollback.
