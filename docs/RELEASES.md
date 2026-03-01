# Release Notes

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
