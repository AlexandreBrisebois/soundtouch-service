# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project aims to follow Semantic Versioning.

## [Unreleased]

### Added

- Versioned scheduler config schema with legacy auto-migration.
- Scheduled weekly CI run for quality and dependency health checks.

### Changed

- Dependency vulnerability audit now blocks CI on failures.
- Contributor workflow now includes required local pre-commit hooks.

### Fixed

- Added explicit migration guidance for the new config schema format.

## [1.9.5.0] - 2026-03-24

### Added

- Mobile-friendly PWA interface for speaker and schedule management.
- Manual schedule trigger endpoint and UI action.
- Schedule pause and resume support.
- Fade in and fade out schedule controls.
- AUX source selection in schedule configuration.

### Changed

- Improved startup and runtime performance using speaker cache architecture.
- Expanded README with deployment and API documentation.

### Fixed

- Reduced delays caused by repeated discovery and status polling.

[Unreleased]: https://github.com/AlexandreBrisebois/soundtouch-service/compare/v1.9.5.0...HEAD
[1.9.5.0]: https://github.com/AlexandreBrisebois/soundtouch-service/releases/tag/v1.9.5.0
