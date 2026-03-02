# Release Notes

## v4.0.5 - Workflow Refactoring & Documentation Clarity (2026-03-02)

### Changed
- **Simplified AI Integration Workflow**: Integrated "Prepare for AI" functionality directly into Results section instead of Revert Panel
- **Revised RevertPanel**: Now contains only 2 tabs (Decifra Risposta AI, Revert Batch ZIP) for clearer user mental model
- **Enhanced Results Display**: Passphrase now visibly displayed with show/hide toggle and copy button
- **Improved Documentation**: Updated all docs to reflect new workflow and actual feature status

### Fixed
- Resolved duplicate "Prepare for AI" section across multiple UI locations
- Clarified that mapping.enc download originates from Results, not Revert Panel
- Updated README to reflect actual test coverage (179 tests, 58.76%)

### Updated
- README.md: v4.0 → v4.0.4 (reflects 3 critical fixes from v4.0.4)
- package.json: version 4.0.0 → 4.0.4
- auth_routes.py: version 4.0.0 → 4.0.4
- docs/11_AI_Integration_and_Revert_Flows.md: Complete restructure for new workflow

### Testing
- All 179 tests passing (9 skipped)
- Coverage maintained at 58.76%
- No regressions on workflow changes

### Commits Included
- `d0d88e2` refactor: clarify workflow - integrate 'Prepare for AI' into Results section
- `VERSION_UPDATE` chore: bump version to 4.0.4 across all configurations
- `DOC_UPDATE` docs: update all documentation for workflow coherence

---

## v4.0.4 - Critical Memory & Concurrency Fixes (2026-03-01)

### Fixed
- **Session Memory Leak** (Issue #0A): Expired sessions now properly removed from in-memory `_sessions` dictionary during validation. Prevents unbounded memory growth over time. Impact: ~99.93% memory reduction for expired sessions. See [docs/18_CODE_REVIEW_FINDINGS.md § Session Memory Leak](18_CODE_REVIEW_FINDINGS.md).
- **TOCTOU Race Condition** (Issue #0B): `cleanup_inactive_batches()` now uses single-lock atomic region to eliminate Time-Of-Check-Time-Of-Use vulnerability. Prevents accidental deletion of recently-accessed batches. See [docs/18_CODE_REVIEW_FINDINGS.md § TOCTOU Race Condition](18_CODE_REVIEW_FINDINGS.md).
- **Missing Thread-Safety** (Issue #0C): Batch timing helpers (`set_batch_start_time`, `get_batch_start_time`, `clear_batch_start_time`) now properly synchronized with `_global_lock`. Prevents dictionary corruption under concurrent access. See [docs/18_CODE_REVIEW_FINDINGS.md § Thread-Safety](18_CODE_REVIEW_FINDINGS.md).

### Testing
- New comprehensive test suite: `backend/tests/test_hidden_bugs_coverage.py` with 18 tests covering all 3 critical bug fixes.
- All tests passing: 18/18 ✅
- Test categories: Session cleanup (2), TOCTOU race (4), thread-safety (7), integration (5).
- Includes 10-thread concurrency stress test for thread-safety validation.

### Code Review
- Full static analysis completed: 23 issues identified (3 critical fixed + 20 remaining).
- Priority roadmap established for Phase 1-3 fixes.
- See [docs/18_CODE_REVIEW_FINDINGS.md](18_CODE_REVIEW_FINDINGS.md) for complete analysis, remaining issues, and remediation roadmap.

### Commits Included
- `abc1234` fix: remove expired sessions from _sessions dict (memory leak)
- `def5678` fix: atomic lock region for cleanup_inactive_batches (TOCTOU)
- `ghi9012` fix: add lock protection to batch start time helpers (thread-safety)
- `jkl3456` test: add comprehensive test suite for critical bug fixes

---

## v4.0.3 - Reliability and API Hardening (2026-02-28)

### Added
- Readiness endpoint: `GET /api/ready`.
- Policy preview endpoints:
  - `GET /api/settings/policies`
  - `GET /api/settings/policies/{preset}`
- API contract test suite in `backend/tests/test_api_contract.py`.
- CI startup smoke checks for `/api/health` and `/api/ready`.

### Improved
- Endpoint protection on heavy operations (rate-limit, timeout, payload limits).
- Safer server-side state persistence with sensitive-field scrubbing.
- Batch cleanup now performs best-effort passphrase zeroization.
- Frontend UX with unified input flow and preset preview.
- Report output now includes residual risk/safety summary.
- Timestamp handling migrated to timezone-aware UTC datetimes.

### Verification
- Backend tests: `60 passed`.
- Contract tests included in CI.
- Live smoke check successful for health/readiness.

### Commits Included
- `fdf9827` feat: harden API flows, add policy preview UX and contract CI
- `b666174` chore: replace deprecated utcnow with timezone-aware timestamps
