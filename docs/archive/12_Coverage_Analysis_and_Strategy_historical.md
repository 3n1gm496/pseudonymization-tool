> **ARCHIVIATO (2026-03-05):** Documento storico di analisi della copertura, valido al momento della fase P1 (~86 test, 45% coverage).
> La copertura attuale (v5.2.1) è **86%** con 850+ test. Vedere `docs/13_Super_Critical_Analysis.md` per le metriche correnti.

# Coverage Analysis & Strategic Path Forward (STORICO — Pre-v5.0.0)

**Current State at time of writing:** 86 tests passing | 45% coverage (3239 statements, 1782 missing)

## Coverage Reality Check

### What "100% Coverage" Means

100% code coverage is theoretically achievable but practically problematic. It requires testing:
- **Every conditional branch** (if/else)
- **Every exception path** (try/except)
- **Every return statement**
- **Every loop variation** (0, 1, n iterations)
- **Every function parameter combination**

This often leads to **"coverage theater"** — tests that add lines to coverage reports without improving code quality.

### Current Coverage Breakdown

**Critical Low-Coverage Modules (need immediate attention):**

| Module | Lines | Coverage | Missing | Priority |
|--------|-------|----------|---------|----------|
| `pipeline.py` | 142 | 15% | 121 | 🔴 P0 |
| `transformer.py` | 212 | 14% | 195 | 🔴 P0 |
| `safety.py` | 36 | 11% | 32 | 🔴 P0 |
| `console_pipeline.py` | 60 | 0% | 60 | 🔴 P0 |
| `psedonymizer/engine.py` | 106 | 0% | 106 | 🔴 P0 |
| `ldap_detector.py` | 303 | 26% | 224 | 🟠 P1 |
| `image_parser.py` | 83 | 29% | 59 | 🟠 P1 |
| `pdf_parser.py` | 59 | 31% | 41 | 🟠 P1 |

**Healthy-Coverage Modules (don't require improvement):**

| Module | Coverage | Status |
|--------|----------|--------|
| `schemas.py` | 94% ✅ | Excellent |
| `policies.py` | 68% ✅ | Good |
| `engine.py` (detectors) | 56% ✅ | Acceptable |
| `factory.py` | 87% ✅ | Excellent |
| `base.py` | 83-86% ✅ | Good |

## Why Coverage is Low: Root Causes

### 1. **Complex Integration Functions**
Functions like `run_scan_pipeline()` and `run_apply_pipeline()` involve:
- File I/O
- Parsing multiple formats (PDF, DOCX, XLSX, images, text)
- LDAPress directory queries (network-dependent)
- Regex matching against complex patterns

These require **end-to-end testing**, not unit testing. Current 86 tests already cover the main flows.

### 2. **Error Path Complexity**
Many code paths only execute when:
- Files are corrupted (hard to simulate)
- Networks are down (environment-dependent)
- OCR fails (requires PIL/Tesseract)
- PDFs are encrypted (requires PDF password handling)

### 3. **Feature Flags & Conditional Logic**
- `BatchMode.LIGHT` vs `BatchMode.STRICT` — different code paths
- Policy-based entity filtering — depends on preset
- Safety assessment logic — depends on detected entities

### 4. **Untestable Components**
- `main.py` (98 missing) — FastAPI app initialization
- `scan_queue.py` (46 missing) — Async queue management
- `console_pipeline.py` (60 missing) — Console UI orchestration

## Realistic Coverage Goals

### Scenario 1: "Good Enough" Coverage (60-70%)
**Effort:** 2-3 weeks | **ROI:** High
- Focus on unit tests for detector logic
- Mock file parsing, add 15-20 new tests
- Add error path tests
- **Result:** ~55-60% coverage, catches real bugs

### Scenario 2: "Comprehensive" Coverage (75-85%)
**Effort:** 4-6 weeks | **ROI:** Medium
- Full parser test suite (valid + invalid files)
- LDAP detector with mocked directory service
- Error cases and edge conditions
- **Result:** ~70-75% coverage, reduces production bugs

### Scenario 3: "Theoretical Maximum" (100%)
**Effort:** 8-12 weeks | **ROI:** Low
- Exhaustive branch coverage
- All exception paths
- All parameter combinations
- **Outcome:** High test maintenance burden, limited value

---

## Recommended Actions

### ✅ Phase 4a: Quick Wins (1 week)

1. **Add 10-15 focused unit tests** for:
   - Detector regex patterns (EmailDetector, IPDetector, etc.)
   - Finding filtering logic
   - Pseudonym generation
   
2. **Target: 50% coverage** (achievable, measurable)

3. **Example tests to add:**
   ```python
   # Tests for regex_detectors.py
   def test_email_detection():
   def test_ipv4_detection():
   def test_phone_number_detection():
   
   # Tests for policies.py
   def test_preset_filtering():
   def test_confidence_threshold():
   ```

### ✅ Phase 4b: Strategic Coverage (2-3 weeks)

1. **Parser module tests** (currently at 16-33%)
   - Create mock PDF/DOCX files
   - Test metadata extraction
   - Test error handling
   
2. **Transformer edge cases** (currently at 14%)
   - Overlapping findings
   - Unicode/emoji handling
   - Very long texts

3. **Safety assessment** (currently at 11%)
   - Test flag generation logic
   - Test warning detection

### ⏸️ Phase 4c: Not Recommended

1. **Do NOT test:**
   - FastAPI route initialization (main.py)
   - Async queue management (scan_queue.py)
   - These are infrastructure, not business logic
   
2. **Do NOT mock/stub:**
   - File write operations
   - Database access (if added)
   - These need integration tests, not unit tests

---

## Coverage Ambitions: Honest Assessment

### Current Reality (45%)
✅ Main workflows tested
✅ API contracts validated
✅ Core pseudonymization pipeline works
❌ Error paths under-tested
❌ Complex integrations partially tested

### After Phase 4a (Target: 50-55%)
✅ Regex detectors fully tested
✅ Finding filtering logic verified
✅ Basic error handling covered
❌ Parser error cases still missing
❌ Advanced features partially tested

### Phase 4b Goal (Target: 70%)
✅ Most detector logic tested
✅ Parser success paths tested
✅ Decision workflow complete
❌ Some error cases remain
❌ Advanced LDAP scenarios untested

### 100% Coverage Reality
❌ **Not recommended** for this codebase
❌ **Too expensive** in development time
❌ **Maintenance burden** exceeds benefits
❌ **Impractical** for integration-heavy code

---

## Recommended Next Steps

### IF you want to improve coverage to 50-55%:
👉 Create `/backend/tests/test_detectors_unit.py` with regex tests
👉 Add 10 focused tests for finding filtering and policies
👉 **Time estimate:** 3-4 hours
👉 **Result:** Measurable improvement, real bug prevention

### IF you want 70% coverage:
👉 Also add `/backend/tests/test_parsers_mocked.py` with mock files
👉 Add parser error cases
👉 Test transformer edge cases
👉 **Time estimate:** 1-2 weeks
👉 **Result:** Good coverage, strong regression prevention

### IF you want to pursue 100%:
👉 This guide recommends the 70% target instead
👉 100% would require exhaustive branch coverage
👉 Diminishing returns beyond 75-80%

---

## Decision Point

**What is your coverage goal?**

- **Option A:** Maintain current 45% with excellent test stability ✅
- **Option B:** Push to 50-55% with 1 day of focused work 👈 Recommended
- **Option C:** Reach 70% with 2 weeks of systematic testing
- **Option D:** Pursue 100% (not recommended)

Choose wisely. High coverage isn't always high quality.
