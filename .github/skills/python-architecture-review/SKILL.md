---
name: python-architecture-review
description: 'Expert Python architecture and best-practices review workflow. Use for design reviews, refactoring plans, maintainability checks, API/service boundaries, reliability, security, performance, and test strategy in Python codebases.'
argument-hint: 'Provide scope, changed files, constraints, and desired depth: quick, standard, or deep.'
user-invocable: true
---

# Python Architecture Review

## What This Skill Produces
- A prioritized architecture and best-practices review focused on correctness, maintainability, security, and operational readiness.
- Concrete findings with severity, evidence, and specific remediation steps.
- A practical improvement plan with low-risk quick wins and higher-impact structural changes.

## When to Use
- Reviewing pull requests or feature branches in Python services.
- Auditing module boundaries, layering, or domain modeling before scaling a system.
- Preparing refactors to reduce coupling, improve testability, or remove technical debt.
- Validating production-readiness for observability, failure handling, and performance.

## Inputs
- Target scope: repository, package, module, or pull request.
- Runtime constraints: Python version, framework, deployment model, SLA/SLO, and data sensitivity.
- Business constraints: delivery timeline, backward compatibility, and allowed dependencies.
- Review depth: quick, standard, or deep.

## Defaults
- If depth is not specified, use standard depth.
- Prioritize architecture and maintainability findings first, then reliability/security, then performance, then testing gaps.

## Procedure
1. Frame the review
- Confirm scope and constraints.
- Identify critical paths first: request handling, data access, background jobs, and external integrations.
- Set review depth:
  - quick: high-signal risks and obvious anti-patterns
  - standard: architecture, reliability, and test posture
  - deep: full design and operational readiness assessment

2. Map system structure
- Identify package boundaries and dependency direction.
- Locate entry points (API routes, CLI, workers, schedulers).
- Trace shared utilities and cross-cutting concerns (config, logging, auth, caching).
- Flag layering violations and circular dependencies.

3. Evaluate architecture decisions
- Check separation of concerns: transport, domain logic, infrastructure.
- Verify explicit interfaces around external systems.
- Assess state management, idempotency, and side-effect boundaries.
- Confirm error taxonomy and failure propagation strategy.

4. Review Python best practices
- Typing and contracts: type hints, dataclass/pydantic usage, and API contracts.
- Resource management: context managers, timeouts, retries, and cleanup paths.
- Concurrency correctness: async boundaries, blocking calls, and shared mutable state.
- Configuration hygiene: environment-driven config, defaults, and validation.
- Logging quality: structured logs, cardinality control, and trace correlation.

5. Assess reliability, security, and performance
- Reliability: retry policies, backoff, circuit breaking, and graceful degradation.
- Security: input validation, secrets handling, authn/authz checks, and unsafe deserialization.
- Performance: I/O hotspots, N+1 patterns, cacheability, and algorithmic complexity.
- Operability: health checks, metrics, alerts, and runbook clarity.

6. Verify test strategy
- Confirm unit tests for domain rules and edge cases.
- Confirm integration tests for boundaries and external contracts.
- Check regression tests for previously fixed defects.
- Identify test gaps by risk, not only by coverage percentage.

7. Produce findings and plan
- Report findings ordered by severity: critical, high, medium, low.
- Within each severity, prioritize architecture and maintainability findings first.
- For each finding include:
  - why it matters
  - where it appears (file/symbol)
  - recommended change
  - risk of change and rollout notes
- End with:
  - quick wins (1-3 days)
  - medium refactors (1-2 sprints)
  - strategic architecture improvements (quarter-scale)

## Decision Points
- If deadlines are tight: prioritize correctness and reliability over broad structural changes.
- If service is customer-facing and latency-sensitive: prioritize timeout, retry, and profiling work.
- If handling sensitive data: elevate security findings and stricter validation requirements.
- If test gaps are large: require targeted integration tests before non-trivial refactors.

## Quality Gates
- No critical correctness or security issues remain unaddressed.
- Dependency flow is intentional and documented.
- External call paths have explicit timeout and failure handling.
- Logging and metrics support production debugging.
- Test plan covers primary risks and known failure modes.

## Output Format
1. Context and scope
2. Top findings by severity
3. Architecture observations
4. Best-practice compliance notes
5. Test gaps and recommendations
6. Prioritized remediation roadmap

## Example Prompts
- /python-architecture-review Review this FastAPI service for architecture risks and Python best practices. Focus on reliability and test strategy.
- /python-architecture-review Deep review of this PR with emphasis on async correctness, dependency boundaries, and production readiness.
- /python-architecture-review Quick pass: identify highest-risk issues in the scheduler and API integration layers.
