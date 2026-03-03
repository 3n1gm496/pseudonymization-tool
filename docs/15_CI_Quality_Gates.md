# CI Quality Gates Configuration

**Version:** 2.0  
**Date:** 2026-03-03  
**Purpose:** Enforceable quality gates to prevent regressions in critical modules

> **Note:** This document reflects the actual CI configuration in `.github/workflows/ci.yml` as of v5.0.0.
> The thresholds were updated in PR #6 to reflect real measured coverage values.

---

## Coverage Thresholds

### Global Coverage
- **Minimum:** **60%**
- **Enforcement:** CI fail if total coverage drops below threshold
- **Rationale:** Baseline quality standard for entire codebase (raised from 50% in v5.0.0)

### Critical Module Coverage

These modules have higher standards due to security/reliability impact:

| Module | Minimum Threshold | Rationale |
|--------|-------------------|-----------|
| `app.core.safety` | **90%** | Safety label logic protects users from data leakage |
| `app.mapping.crypto` | **90%** | AES-GCM encryption is core security guarantee |
| `app.pseudonymizer.engine` | **90%** | Pseudonym generation correctness is critical |
| `app.core.auth` | **75%** | Authentication must be well-tested |
| `app.core.pipeline` | **65%** | Pipeline orchestration is critical path |
| `app.pseudonymizer.transformer` | **50%** | Transformation correctness |
| `app.core.exceptions` | **55%** | Exception taxonomy must be well-tested |

### CI Workflow (actual `.github/workflows/ci.yml`)

```yaml
- name: Run tests (unit + functional, exclude integration)
  run: |
    pytest tests/ \
      -m "not integration" \
      --cov=app \
      --cov-report=xml \
      --cov-fail-under=60

- name: Coverage regression check for critical modules
  run: |
    pytest tests/ -m "not integration" --cov=app.core.safety    --cov-fail-under=90 -q
    pytest tests/ -m "not integration" --cov=app.mapping.crypto  --cov-fail-under=90 -q
    pytest tests/ -m "not integration" --cov=app.core.auth       --cov-fail-under=75 -q
    pytest tests/ -m "not integration" --cov=app.core.pipeline   --cov-fail-under=65 -q
    pytest tests/ -m "not integration" --cov=app.pseudonymizer.engine --cov-fail-under=90 -q
    pytest tests/ -m "not integration" --cov=app.pseudonymizer.transformer --cov-fail-under=50 -q
    pytest tests/ -m "not integration" --cov=app.core.exceptions --cov-fail-under=55 -q
```

---

## Exception Handling Standards

### Banned Patterns in Critical Modules

The following patterns are **prohibited** in modules listed below unless explicitly justified with inline comment:

```python
# ❌ BANNED: Untyped broad exception (no comment)
try:
    risky_operation()
except Exception:
    pass

# ❌ BANNED: Catch-all with generic handling
try:
    risky_operation()
except Exception as e:
    logger.error(str(e))  # Too generic

# ✅ ALLOWED: Specific exception with recovery
try:
    risky_operation()
except ParsingError as e:
    # Justification: parsing errors are expected and recoverable
    return fallback_value

# ✅ ALLOWED: Broad exception with justification
try:
    third_party_lib.do_thing()
except Exception as e:  # JUSTIFICATION: lib can throw arbitrary exceptions, we log and re-raise
    logger.error("Third party failure", exc_info=True)
    raise
```

### Critical Modules with Exception Standards

- `app/core/pipeline.py`
- `app/core/safety.py`
- `app/pseudonymizer/transformer.py`
- `app/mapping/crypto.py`
- `app/api/batches_routes.py` (apply/review endpoints)

### CI Check Implementation

```bash
# Fail build if untyped broad exceptions found (no comment justification)
grep -rn "except Exception" <critical_file.py> | grep -v "#" | grep -v "except Exception as"
```

---

## Additional Quality Gates

### Code Complexity
- **Max Cyclomatic Complexity:** 10 (flake8 `--max-complexity=10`)
- **Enforcement:** Warning (future: fail)
- **Rationale:** High complexity correlates with defects

### Security Scanning
- **Tool:** Bandit (severity >= LOW)
- **Enforcement:** Fail on HIGH or MEDIUM findings
- **Rationale:** Prevent common security anti-patterns

### Dependency Vulnerabilities
- **Tool:** **pip-audit** (PyPI vulnerability DB via OSV)
- **Enforcement:** Fail on any vulnerability found
- **Rationale:** Known CVEs must not be deployed (replaced `safety` in PR #6)

### Unused Imports
- **Tool:** flake8 `--select=F401`
- **Enforcement:** Fail on any unused import in `app/` (not tests)
- **Rationale:** Dead code increases maintenance burden

---

## CI Workflow Integration

### GitHub Actions Steps (v5.0.0)

```yaml
- name: Run tests (unit + functional, exclude integration)
  run: pytest tests/ -m "not integration" --cov=app --cov-fail-under=60

- name: Coverage regression check for critical modules
  run: |
    pytest tests/ -m "not integration" --cov=app.core.safety    --cov-fail-under=90 -q
    pytest tests/ -m "not integration" --cov=app.mapping.crypto  --cov-fail-under=90 -q
    pytest tests/ -m "not integration" --cov=app.core.auth       --cov-fail-under=75 -q
    pytest tests/ -m "not integration" --cov=app.core.pipeline   --cov-fail-under=65 -q
    pytest tests/ -m "not integration" --cov=app.pseudonymizer.engine --cov-fail-under=90 -q
    pytest tests/ -m "not integration" --cov=app.pseudonymizer.transformer --cov-fail-under=50 -q
    pytest tests/ -m "not integration" --cov=app.core.exceptions --cov-fail-under=55 -q

- name: Security scan (Bandit)
  run: bandit -r app/ -ll -q

- name: Dependency vulnerability scan (pip-audit)
  run: pip-audit --requirement requirements.txt

- name: Unused imports check
  run: flake8 app/ --select=F401
```

---

## Enforcement Policy

### Pull Request Requirements

All PRs must pass:
1. ✅ Global coverage >= **60%**
2. ✅ Critical module coverage >= thresholds
3. ✅ No untyped broad exceptions in critical paths
4. ✅ Bandit security scan (no HIGH/MEDIUM issues)
5. ✅ pip-audit (0 CVE)
6. ✅ flake8 F401 (0 unused imports in app/)

### Exemption Process

If a legitimate use case requires exemption:
1. Add inline comment with `# QG-EXEMPT: <reason>`
2. Document in PR description
3. Require maintainer approval

Example:
```python
try:
    legacy_system.call()
except Exception as e:  # QG-EXEMPT: legacy system uses dynamic exceptions, no typed alternatives
    handle_generic(e)
```

---

## Monitoring and Reporting

### Coverage Trends

Track coverage over time:
- **Codecov:** Automatic PR comments with delta
- **Local:** `make test-cov` generates HTML report to `htmlcov/`

### Quality Dashboard (Future)

Proposed metrics:
- Coverage trend (7-day moving average)
- Exception pattern violations (count per module)
- Complexity hotspots (top 10 functions)
- Security findings (age and severity)

---

## Rationale and Trade-offs

### Why These Thresholds?

- **60% global:** Raised from 50% in v5.0.0 — reflects actual measured coverage
- **90% crypto/safety/engine:** Core security modules must be thoroughly tested
- **75% auth:** Authentication is a critical security boundary
- **65% pipeline:** Main orchestration path, gradually increasing
- **55% exceptions:** Exception taxonomy must be exercised

### Why Not Higher?

- **Pragmatism:** Retroactive 100% coverage is cost-prohibitive
- **Incremental:** Thresholds ratchet up over time (see roadmap)
- **Focus:** Better to have quality tests in critical areas than 100% trivial tests

### Why pip-audit instead of Safety?

- `safety` was replaced in PR #6 because it had false negatives (missed known CVEs)
- `pip-audit` uses the OSV database and is more reliable
- `safety` free tier has limited coverage; `pip-audit` is fully open source

---

## Maintenance

### Updating Thresholds

When actual coverage increases sustainably (3+ consecutive weeks):
1. Update threshold in `.github/workflows/ci.yml`
2. Update this document
3. Announce in PR description

### Annual Review

Re-evaluate gates annually:
- Are thresholds still realistic?
- Are banned patterns still relevant?
- Should new modules be added to critical list?

---

## References

- [.github/workflows/ci.yml](../.github/workflows/ci.yml) - CI implementation (source of truth)
- [docs/13_Super_Critical_Analysis.md](13_Super_Critical_Analysis.md) - P2-2 requirement
- [docs/07_Test_Plan_and_Metrics.md](07_Test_Plan_and_Metrics.md) - Overall test strategy
- [pyproject.toml](../pyproject.toml) - Pytest/coverage configuration

---

## Success Metrics

Quality gates are successful when:
- ✅ CI fails on coverage regression in critical modules
- ✅ CI fails on untyped broad exceptions in critical paths
- ✅ CI fails on any CVE (pip-audit)
- ✅ Developer feedback: "Gates are helpful, not annoying"
- ✅ Zero production incidents from untested critical paths (6-month window)

**Status:** Updated 2026-03-03 (v5.0.0)
