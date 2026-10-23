# Tasks

## 1. Shared callback-origin resolution

- [x] 1.1 Add focused tests for canonical explicit origins, one eligible inferred address, deduplication, zero/multiple-address errors, malformed platform output, and invalid explicit origins; verify failures identify the missing resolver behavior.
- [x] 1.2 Implement the dependency-free, bounded platform resolver and strict private-origin validator; verify the focused resolver tests pass without live network access.

## 2. Safe startup integration

- [x] 2.1 Resolve and export `WISP_BASE_URL` in native `task up` before creating startup state, while preserving port, run-marker, process-identity, and shutdown checks; verify Taskfile contract tests pass.
- [x] 2.2 Reuse the same resolver in `container:up` before container ownership, state, build, or run mutations, preserving explicit overrides and all Docker/state safeguards; verify container task tests pass.
- [x] 2.3 Update local/container startup documentation with automatic single-address behavior and explicit ambiguity fallback; verify commands and messages match the tested interface.

## 3. Integration evidence

- [x] 3.1 Run the complete isolated automated suite and strict OpenSpec validation, recording unrelated failures separately and leaving the running application and speakers untouched.
- [x] 3.2 Obtain independent review of URL validation, interface parsing, pre-mutation ordering, and unchanged startup ownership/safety boundaries before archiving.

## Workflow follow-up

- On the next separately authorized restart, confirm the selected origin is reachable from the speaker before relying on unattended relay schedules.
