# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.1.0] - 2026-03-03

### Added
- **Production Readiness**:
  - **Dependency Lock File**: Added `requirements.lock` and `requirements-dev.lock` for deterministic production builds. The Dockerfile and CI now use these lock files. (#26)
  - **Security Headers**: Added a middleware to inject security headers (`X-Content-Type-Options`, `X-Frame-Options`, etc.) in all HTTP responses. (#27)
  - **Secrets Validation**: The application now validates the presence of critical environment variables (`SECRET_KEY`, `ENCRYPTION_KEY`) at startup in production. (#27)
  - **Graceful Shutdown**: Implemented graceful shutdown for the backend, ensuring that the background cleanup scheduler is stopped correctly. (#28)
  - **Enhanced Health/Ready Probes**: The `/api/ready` endpoint now checks for the availability of all dependencies (Redis, temp directories) before reporting a ready state. (#28)
- **Operational Documentation**:
  - Added `docs/RUNBOOK.md` with instructions for deployment, monitoring, and emergency procedures. (#30)
  - Added `docs/DEPLOYMENT_CHECKLIST.md` to ensure safe production deployments. (#30)
- **Test Coverage**:
  - Added 12 new tests for `ldap_client.py` and `ldap_detector.py` using mock `ldap3`, increasing coverage from ~40-50% to **95-97%**. (#29)
  - Added 10 new tests for `transformer.py`, increasing its coverage from 55% to **78%**. (#25)

### Changed
- **Test Suite**: Total tests increased from ~267 to **420 passed**, with 11 legitimate skips. (#25, #29)
- **Global Coverage**: Increased global test coverage from 65% to **77%**. (#25, #29)
- **CI Workflow**: The CI workflow now uses the new lock files and has updated coverage thresholds. (#26)
- **Code Quality**: Refactored `image_parser.py` to correctly use `avg_conf` and removed unused variables and f-strings from `pipeline.py` and `text_parser.py`. (#25)

### Fixed
- **Hardcoded Test Skip**: Removed a hardcoded `@pytest.mark.skip` in `test_phase4a_auth_logging.py` that was incorrectly skipping a test. (#25)
- **File Permissions**: Removed executable permissions from `requirements.txt` and legacy `.bat` files. (#25)
- **Missing Directory in Tests**: Added a `.gitkeep` to the `backend/config/dictionaries` directory to ensure it exists during tests, fixing failures in the `/api/ready` probe. (#28)
- **Documentation**: Aligned all documentation (README, architecture docs) with the actual state of the project (v5.0.0, 348+ tests, 71%+ coverage). (#24)

## [5.0.0] - 2026-03-03

### Added
- **Frontend ErrorBoundary**: Added a React ErrorBoundary component to catch unhandled JavaScript errors. (#21)
- **CSRF Token Bootstrap**: The `/api/auth/me` endpoint now includes the CSRF token in the `X-CSRF-Token` response header. (#21)
- **Passphrase Encryption**: The on-disk passphrase file is now encrypted using AES-256-GCM. (#17)
- **`CONTRIBUTING.md`** and **`CHANGELOG.md`**. (#22)

### Changed
- **Dependencies**: Upgraded `pypdf` to `6.7.4` to fix 13 CVEs and pinned frontend dependencies. (#1)
- **CI**: Hardened the CI pipeline with `pip-audit`, Python 3.11/3.12 matrix, and realistic coverage thresholds. (#6)
- **Code Quality**: Removed 72 unused imports, fixed security issues from `bandit`, and applied `black`/`isort`. (#8, #15)

### Fixed
- **Frontend Polling**: Implemented `AbortController` to cancel pending polling requests. (#12)
- **Docker Security**: Hardened the Dockerfile and Docker Compose setup (non-root user, isolated Redis, secrets from `.env`). (#2, #3)
- **Authentication Security**: Hardened `auth.py` with secrets in `STATE_DIR` and race condition fixes. (#4)

### Removed
- **Hardcoded Credentials**: Removed the `admin123!` password from tests. (#17)
