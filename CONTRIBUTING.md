# Contributing to Wisp

Thanks for taking the time to contribute.

## What We Value

- Reliable behavior on real SoundTouch hardware.
- Clear and testable code changes.
- Respectful collaboration and constructive feedback.

## Getting Started

1. Fork the repository.
2. Create a feature branch from main.
3. Install dependencies.
4. Run the app and tests locally before opening a pull request.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt ruff mypy pre-commit
pre-commit install
pre-commit run --all-files
python -m app.main
pytest -q
```

Pre-commit hooks are part of the expected contributor workflow and should be run before opening a pull request.

## Pull Request Guidelines

- Keep PRs focused and small when possible.
- Include a clear problem statement and solution summary.
- Add or update tests when behavior changes.
- Update README and docs for user-facing changes.
- Ensure all tests pass before requesting review.

## Suggested Commit Format

Use concise commit messages that explain intent, for example:

- feat: add run-now schedule endpoint
- fix: prevent cache miss during speaker status lookup
- docs: clarify host network deployment notes

## Reporting Bugs

When opening an issue, include:

- Environment details (OS, Docker version, NAS model if relevant).
- Steps to reproduce.
- Expected behavior vs actual behavior.
- Logs or API responses if available.

## Feature Requests

Feature requests are welcome. Please explain:

- The use case and user impact.
- Why current behavior is insufficient.
- Any proposed API or UI changes.

## Scope Notes

This project is focused on Bose SoundTouch local-network automation and control.
Cloud services and vendor account integrations are currently out of scope.
