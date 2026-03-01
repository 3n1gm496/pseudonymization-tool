# CI Quality Gates Configuration

**Version:** 1.0  
**Date:** 2026-03-01  
**Purpose:** Enforceable quality gates to prevent regressions in critical modules

---

## Coverage Thresholds

### Global Coverage
- **Minimum:** 50%
- **Enforcement:** CI fail if total coverage drops below threshold
- **Rationale:** Baseline quality standard for entire codebase

### Critical Module Coverage

These modules have higher standards due to security/reliability impact:

| Module | Current Coverage | Minimum Threshold | Rationale |
|--------|------------------|-------------------|-----------|
| `app.core.exceptions` | 58% | **55%** | Exception taxonomy must be well-tested for proper error handling |
| `app.core.pipeline` | 12% | **20%** | Pipeline orchestration is critical path, gradually increasing |
| `app.core.safety` | 11% | **20%** | Safety label logic protects users from data leakage |
| `app.pseudonymizer.transformer` | 31% | **35%** | Transformation correctness is core security guarantee |
| `app.parsers.*` | ~40% avg | **40%** | Parser robustness prevents silent data loss |
| `app.detectors.regex_detectors` | 52% | **50%** | Regex accuracy directly impacts PII detection |

### Future Targets (6-month roadmap)

| Module | Current | 3-month Target | 6-month Target |
|--------|---------|----------------|----------------|
| `app.core.pipeline` | 12% | 30% | 50% |
| `app.core.safety` | 11% | 25% | 50% |
| `app.pseudonymizer.transformer` | 31% | 50% | 70% |

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
- `app/pseudonyimzer/transformer.py`
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
- **Tool:** Safety (PyPI vulnerability DB)
- **Enforcement:** Warning (fail on CRITICAL in future)
- **Rationale:** Known CVEs should not be deployed

---

## CI Workflow Integration

### GitHub Actions Steps

```yaml
- name: Run tests with pytest
  run: pytest tests/ --cov=app --cov-fail-under=50

- name: Coverage regression check for critical modules
  run: |
    pytest tests/ --cov=app.core.pipeline --cov-fail-under=20
    pytest tests/ --cov=app.core.safety --cov-fail-under=20
    pytest tests/ --cov=app.pseudonymizer.transformer --cov-fail-under=35
    pytest tests/ --cov=app.core.exceptions --cov-fail-under=55

- name: Check for untyped broad exceptions
  run: |
    BROAD=$(grep -rn "except Exception" backend/app/core/pipeline.py | grep -v "#" | grep -v "except Exception as")
    if [ -n "$BROAD" ]; then exit 1; fi
```

---

## Enforcement Policy

### Pull Request Requirements

All PRs must pass:
1. ✅ Global coverage >= 50%
2. ✅ Critical module coverage >= thresholds
3. ✅ No untyped broad exceptions in critical paths
4. ✅ Bandit security scan (no HIGH/MEDIUM issues)
5. ✅ Black/isort/flake8 formatting/linting

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

- **50% global:** Industry baseline for non-trivial projects
- **55% exceptions:** New module, should maintain high bar
- **20% pipeline/safety:** Legacy code, incremental improvement approach
- **35% transformer:** Core logic, higher than avg but realistic given size

### Why Not Higher?

- **Pragmatism:** Retroactive 100% coverage is cost-prohibitive
- **Incremental:** Thresholds ratchet up over time (see roadmap)
- **Focus:** Better to have quality tests in critical areas than 100% trivial tests

### Why Enforce Exceptions?

- **Root cause visibility:** Catch-all exceptions hide bugs
- **Operational clarity:** Typed exceptions enable better monitoring/alerting
- **Recovery logic:** Specific exceptions allow targeted recovery strategies

---

## Maintenance

### Updating Thresholds

When actual coverage increases sustainably (3+ consecutive weeks):
1. Update threshold in `.github/workflows/ci.yml`
2. Update this document
3. Announce in team chat/standup

### Annual Review

Re-evaluate gates annually:
- Are thresholds still realistic?
- Are banned patterns still relevant?
- Should new modules be added to critical list?

---

## References

- [.github/workflows/ci.yml](../.github/workflows/ci.yml) - CI implementation
- [docs/13_Super_Critical_Analysis.md](13_Super_Critical_Analysis.md) - P2-2 requirement
- [docs/07_Test_Plan_and_Metrics.md](07_Test_Plan_and_Metrics.md) - Overall test strategy
- [pyproject.toml](../pyproject.toml) - Pytest/coverage configuration

---

## Success Metrics

P2-2 is successful when:
- ✅ CI fails on coverage regression in critical modules
- ✅ CI fails on untyped broad exceptions in critical paths
- ✅ Developer feedback: "Gates are helpful, not annoying"
- ✅ Zero production incidents from untested critical paths (6-month window)

**Status:** Implemented 2026-03-01
