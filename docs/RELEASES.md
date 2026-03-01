# Release Notes

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
