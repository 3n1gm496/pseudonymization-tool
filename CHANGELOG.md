# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.0.0] - 2026-03-03

### Added
- **Frontend ErrorBoundary**: Added a React ErrorBoundary component to catch unhandled JavaScript errors and display a recovery UI instead of a blank page.
- **CSRF Token Bootstrap**: The `/api/auth/me` endpoint now includes the CSRF token in the `X-CSRF-Token` response header, allowing the frontend to bootstrap its CSRF token after a page reload without requiring a new login.
- **Passphrase Encryption**: The on-disk passphrase file is now encrypted using AES-256-GCM to protect it from unauthorized access.
- **`CONTRIBUTING.md`**: Added a contributing guide.
- **`CHANGELOG.md`**: Added this changelog file.

### Changed
- **Dependencies**: Upgraded `reportlab` to `4.x` and `httpx` is now a development dependency.
- **CI**: Updated CI to use Redis 7, updated coverage thresholds, and fixed FastAPI 0.135.1 compatibility issues.
- **Code Quality**: Improved code quality by removing unused imports, fixing security issues reported by `bandit`, and applying `black` and `isort` formatting.
- **Test Coverage**: Increased test coverage for `cache`, `revert_routes`, `tasks`, and `image_parser` modules, raising global coverage from 65% to 71%.

### Fixed
- **Frontend Polling**: Implemented `AbortController` to cancel pending polling requests when the user navigates away from the page.
- **CI**: Fixed a CI failure caused by a change in FastAPI's handling of empty form fields.
- **File Permissions**: Removed executable permissions from all `.md` files.

### Removed
- **Hardcoded Credentials**: Removed the hardcoded `admin123!` password from tests.
- **Unused Component**: Removed the unused `PolicySelector.jsx` component.
