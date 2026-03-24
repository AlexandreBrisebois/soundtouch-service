# Security Policy

## Supported Versions

The latest tagged release and the latest Docker image are considered supported.

## Reporting a Vulnerability

Please do not disclose security vulnerabilities publicly in GitHub issues.

Use one of the following paths:

1. Open a GitHub Security Advisory for this repository.
2. Contact the repository owner privately if advisory access is not available.

Direct advisory link:

- https://github.com/AlexandreBrisebois/soundtouch-service/security/advisories/new

When reporting, include:

- A clear description of the issue and impact.
- Reproduction steps or proof of concept.
- Affected versions and environment details.
- Any suggested remediation.

## Response Expectations

- Initial triage target: within 7 days.
- Status updates provided as remediation progresses.
- Public disclosure coordinated after a fix is available.

## Security Best Practices for Deployments

- Keep the container and host OS updated.
- Run behind trusted local network boundaries.
- Avoid exposing the service directly to the public internet without an authentication layer.
- Use least-privilege access on mounted volumes.
