# CRITICAL ISSUES ANALYSIS — Pseudonymization Tool v4.0

**Date**: March 1, 2026  
**Analyst**: Senior Backend/Frontend Engineer  
**Severity Breakdown**: 🔴 CRITICAL: 3 | 🟠 HIGH: 7 | 🟡 MEDIUM: 8 | 🟢 LOW: 4

---

## 🔴 CRITICAL ISSUES (Must Fix Before Production)

### ⚠️ Issue #1: RACE CONDITION in `batch_manager.py` — Unprotected Dictionary Access

**File**: `backend/app/core/batch_manager.py` (lines 23-80)  
**Severity**: 🔴 CRITICAL  
**Category**: Concurrency / Data Integrity

**The Problem**:
```python
# UNPROTECTED GLOBAL DICTIONARIES — NO LOCKS!
_batches: Dict[str, Batch] = {}
_passphrases: Dict[str, str] = {}
_engines: Dict[str, object] = {}
_decisions: Dict[str, Dict[str, Any]] = {}
_last_activity: Dict[str, float] = {}

# Functions access without mutex:
def get_batch(batch_id: str) -> Optional[Batch]:
    batch = _batches.get(batch_id)  # ❌ TOCTOU race condition
    if batch:
        _last_activity[batch_id] = time.time()  # ❌ Another unraceless access
    return batch
```

**Race Scenario**:
```
Thread 1: Gets batch B1 from _batches
Thread 2: Calls cleanup_batch(B1), deletes from _batches
Thread 1: Tries to update _last_activity[B1] → KeyError OR wrong state
   OR
Thread 1: get_batch(B1) returns batch
Thread 2: cleanup_batch(B1) empties passphrase and deletes entries
Thread 1: Tries apply_review_decisions on now-invalid data
```

**Impact**:
- Data corruption in concurrent scenarios
- Lost findings if cleanup happens during scan
- Passphrase loss for batch in flight
- Potential KeyError crashes

**Fix Required**:
```python
import threading

_global_lock = threading.RLock()  # Reentrant lock for nested calls

def get_batch(batch_id: str) -> Optional[Batch]:
    with _global_lock:
        batch = _batches.get(batch_id)
        if batch:
            _last_activity[batch_id] = time.time()
        return batch

# Apply same lock to: update_batch, create_batch, cleanup_batch
# store_passphrase, get_passphrase, store_decisions, get_decisions
```

---

### ⚠️ Issue #2: FINDING STATE DUPLICATION/INCONSISTENCY — `pipeline.py` Line 145

**File**: `backend/app/core/pipeline.py` (line 145)  
**Severity**: 🔴 CRITICAL  
**Category**: Data Integrity / Logic Error

**The Problem**:
```python
# In run_scan_pipeline():
# Mantieni i finding di testo inline già presenti
existing_text_findings = [f for f in batch.findings if f.is_text_input]
batch.findings = existing_text_findings + all_findings  # ❌ DUPLICATES FINDINGS!
```

**Scenario That Breaks This**:
1. User scans text inline → creates 5 findings (is_text_input=True)
2. Batch status = REVIEW, findings stored in batch
3. User clicks upload files to SAME batch → run_scan_pipeline() called again
4. Previous findings (is_text_input=True) still in batch.findings
5. Code filters: `existing_text_findings = [5 old findings]`
6. Adds new file findings: `all_findings = [3 new findings]`
7. Result: `batch.findings = [5 old + 3 new] = 8 findings` ✅ **CORRECT**

**BUT WAIT — The Real Bug**:
```python
# If same scan runs twice on same batch (network retry, race condition):
# First run: batch.findings = [] + [5 new] = [5]
# Second run: batch.findings = [5 old] + [5 new] = [10]
# User sees "10 findings" but database might have only [5] !
```

**Actual Problem**: Appending without deduplication on findings with same finding_id

**Impact**:
- Duplicate findings in review UI
- User reviews same finding twice (confusion)
- Apply step processes duplicates
- Generated output has redundant replacements

**Fix Required**:
```python
def run_scan_pipeline(batch_id: str) -> Batch:
    # ... rest of code ...
    existing_text_findings = [f for f in batch.findings if f.is_text_input]
    
    # Deduplicate: new findings with same finding_id as existing
    existing_ids = {f.finding_id for f in existing_text_findings}
    unique_new_findings = [f for f in all_findings if f.finding_id not in existing_ids]
    
    batch.findings = existing_text_findings + unique_new_findings
    batch.status = BatchStatus.REVIEW
    update_batch(batch)
```

---

### ⚠️ Issue #3: MEMORY ALLOCATION BUG — `FindingsTable.jsx` Infinite Re-renders

**File**: `frontend/src/components/FindingsTable.jsx` (line 10-15)  
**Severity**: 🔴 CRITICAL  
**Category**: React Performance / Memory Leak

**The Problem**:
```jsx
const FindingsTable = ({ batch, onApply, isLoading }) => {
  const [decisions, setDecisions] = useState(() => {
    return Object.fromEntries(
      batch.findings.map((f) => [
        f.finding_id,
        {
          action: 'accept',
          custom_pseudonym: f.proposed_pseudonym,  // ❌ OBJECT REFERENCE ISSUE
        },
      ])
    )
  })
```

**The Issue**:
- Initializer function runs **once on mount** (correct)
- BUT if parent `App.jsx` does: `setBatch({...oldBatch, findings: [new findings]})`
- React sees `batch` prop changed → **does NOT re-run useState initializer**
- `decisions` state is STILL based on OLD findings
- User reviews old findings, applies to new ones → MISMATCH!

**Scenario**:
1. Load batch with 5 findings → decisions state created with 5 entries
2. User uploads ANOTHER file to same batch
3. Backend returns batch with 10 findings
4. Parent re-renders with new batch prop
5. **decisions still only has 5 entries!**
6. User tries to review → 5 new findings have NO decision entry
7. Apply crashes OR silently ignores 5 findings

**Real Issue**: `useState(() => ...)` only runs on first mount, not on prop changes

**Fix Required**:
```jsx
const [decisions, setDecisions] = useState({})

useEffect(() => {
  // Re-initialize decisions whenever batch.findings changes
  setDecisions(
    Object.fromEntries(
      batch.findings.map((f) => [
        f.finding_id,
        {
          action: 'accept',
          custom_pseudonym: f.proposed_pseudonym,
        },
      ])
    )
  )
}, [batch.findings])  // Dependency array!
```

---

## 🟠 HIGH SEVERITY ISSUES

### Issue #4: MISSING INPUT VALIDATION — `batches_routes.py` Line 345-360

**File**: `backend/app/api/batches_routes.py`  
**Severity**: 🟠 HIGH  
**Category**: Input Validation / Data Integrity

**The Problem**:
```python
@router.post("/batches")
async def create_new_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    mode: str = Form("strict"),           # ❌ STRING, not validated!
    preset: str = Form("SOC Logs"),       # ❌ STRING, not validated!
    passphrase: str = Form(""),           # ❌ Not validated here!
):
```

**Issues**:
1. `mode` could be "invalid_mode" → crashes when creating BatchConfig
2. `preset` could be "nonexistent_policy" → silent failure
3. Empty passphrase not caught → allows weak auth

**Missing Validation**:
```python
# ❌ NOT IN CODE:
if mode not in [m.value for m in BatchMode]:
    raise HTTPException(400, f"Invalid mode: {mode}")

if preset not in [p.value for p in PresetName]:
    raise HTTPException(400, f"Invalid preset: {preset}")

if passphrase and len(passphrase) < 12:
    raise HTTPException(400, "Passphrase must be ≥12 chars")
```

**Fix**: Add Pydantic request model:
```python
class CreateBatchRequest(BaseModel):
    mode: BatchMode  # Enum validation
    preset: PresetName  # Enum validation
    passphrase: str = Field(min_length=0)  # Pydantic validates

@router.post("/batches")
async def create_new_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    body: CreateBatchRequest,
):
    # mode and preset are now validated Enums
```

---

### Issue #5: INCOMPLETE ERROR HANDLING — `apply_batch()` Missing Rollback

**File**: `backend/app/api/batches_routes.py` (line 491-520)  
**Severity**: 🟠 HIGH  
**Category**: Error Handling / Data Consistency

**The Problem**:
```python
@router.post("/batches/{batch_id}/apply")
async def apply_batch(batch_id: str, request: Request):
    batch = get_batch(batch_id)
    if batch.status != BatchStatus.REVIEW:
        raise HTTPException(400, "Batch not in review")
    
    # ❌ NO PRE-CHECK IF PASSPHRASE EXISTS
    zip_path = await asyncio.wait_for(
        run_in_threadpool(run_apply_pipeline, batch_id, started_at),
        timeout=API_HEAVY_TIMEOUT_SECONDS,  # 180 seconds
    )
    # ❌ IF TIMEOUT → partial apply, no state rollback!
    
    # ❌ IF run_apply_pipeline CRASHES halfway:
    # - Some files pseudonymized
    # - Some files not
    # - Batch state inconsistent
```

**Issues**:
1. Timeout (504 error) → batch state partially modified
2. Exception during apply → batch.status left as REVIEW but files processed
3. No transactional consistency

**Required Fix**:
```python
@router.post("/batches/{batch_id}/apply")
async def apply_batch(batch_id: str, request: Request):
    batch = get_batch(batch_id)
    
    # PRE-FLIGHT CHECKS
    if not get_passphrase(batch_id):
        raise HTTPException(400, "Passphrase missing (batch cleanup?)")
    if batch.status != BatchStatus.REVIEW:
        raise HTTPException(400, f"Cannot apply: status={batch.status}")
    
    # SNAPSHOT batch state before apply
    original_status = batch.status
    original_files = [f.model_copy() for f in batch.files]
    
    # APPLY with error handling
    try:
        batch.status = BatchStatus.APPLYING
        update_batch(batch)
        
        zip_path = await asyncio.wait_for(...)
        batch.status = BatchStatus.DONE
        update_batch(batch)
        
    except asyncio.TimeoutError:
        # ROLLBACK
        batch.status = original_status
        batch.files = original_files
        update_batch(batch)
        raise HTTPException(504, "Apply timeout, batch state restored")
    except Exception as e:
        # ROLLBACK
        batch.status = original_status
        batch.files = original_files
        update_batch(batch)
        raise HTTPException(500, f"Apply failed: {e}")
```

---

### Issue #6: SILENT FAILURE — Missing Error Response in Frontend

**File**: `frontend/src/components/Scanner.jsx` (line 26)  
**Severity**: 🟠 HIGH  
**Category**: UX / Error Handling

**The Problem**:
```jsx
const handleTextScan = async (e) => {
    e.preventDefault()
    if (!text.trim()) {
      showToast('Inserisci del testo da scansionare', 'warning')
      return
    }

    try {
      const response = await axios.post('/api/console/scan', {
        text,
      })
      onScan({ ...response.data, is_text_input: true, source_text: text })
      showToast('Scan completato', 'success')
    } catch (error) {
      showToast(error.response?.data?.detail || 'Errore durante lo scan', 'error')
      // ❌ Flow continues! isLoading prop still true, parent component still waiting
    }
  }
```

**Missing**: Reset parent isLoading state on error

**Issue**: If parent is `<Scanner isLoading={isLoading} />`, after error:
- Toast shows error
- But isLoading remains true
- UI looks frozen
- User can't click scan again

**Fix**:
```jsx
const handleTextScan = async (e) => {
    e.preventDefault()
    if (!text.trim()) {
      showToast('Inserisci del testo da scansionare', 'warning')
      return
    }

    try {
      const response = await axios.post('/api/console/scan', {
        text,
      })
      onScan({ ...response.data, is_text_input: true, source_text: text })
      showToast('Scan completato', 'success')
    } catch (error) {
      showToast(error.response?.data?.detail || 'Errore durante lo scan', 'error')
    } finally {
      // ✅ Reset loading state on error
      // Parent must pass setIsLoading or resetLoading callback
    }
  }
```

---

### Issue #7: Passphrase Not Validated Before Apply — `batches_routes.py` Line 475

**File**: `backend/app/api/batches_routes.py`  
**Severity**: 🟠 HIGH  
**Category**: Data Integrity

**Code**:
```python
@router.post("/batches/{batch_id}/apply")
async def apply_batch(batch_id: str, request: Request):
    batch = get_batch(batch_id)
    
    # ❌ NO CHECK: Is passphrase still in memory?
    # If batch.batch_id was cleaned up, passphrase is gone!
    # Mapping file will fail to decrypt later
```

**Scenario**:
1. User uploads batch B1
2. Passphrase stored in `_passphrases[B1]`
3. Batch cleanup triggered (inactivity timeout = 300s)
4. `cleanup_batch(B1)` runs → `_passphrases.pop(B1)`
5. User immediately clicks Apply (before frontend knows cleanup happened)
6. Apply tries to build mapping.enc with deleted passphrase
7. Mapping encryption fails
8. User downloads broken ZIP

**Fix**:
```python
@router.post("/batches/{batch_id}/apply")
async def apply_batch(batch_id: str, request: Request):
    batch = get_batch(batch_id)
    
    # ✅ VALIDATE: Passphrase still exists
    if not get_passphrase(batch_id):
        raise HTTPException(
            status_code=410,  # Gone
            detail="Batch passphrase lost (session timed out). Please re-scan."
        )
    
    # ... rest of apply ...
```

---

### Issue #8: MISSING UNIQUE CONSTRAINT on finding_id

**File**: `backend/app/models/schemas.py` + `backend/app/core/pipeline.py`  
**Severity**: 🟠 HIGH  
**Category**: Data Integrity

**Issue**: Finding IDs are supposed to be unique per batch, but:
- No constraint prevents duplicates
- If two detectors find same entity → both get different finding_id
- Deduplication in `run_text_scan` only checks `is_text_input` flag, not actual uniqueness

**Example**:
```
Text: "John Doe john@example.com"
- RegexNameDetector finds "John Doe" → finding_id = uuid1
- DictionaryDetector finds same "John Doe" → finding_id = uuid2
- Both added to batch.findings
- User sees SAME entity twice with different IDs
- Apply runs TWICE for same entity
```

**Fix**: Deduplicate by (entity_type, original_value) before adding:
```python
def _deduplicate_findings(findings: List[Finding]) -> List[Finding]:
    """Remove findings with duplicate (entity_type, original_value)."""
    seen = set()
    unique = []
    for f in findings:
        key = (f.entity_type, f.original_value, f.file_id)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique
```

---

## 🟡 MEDIUM SEVERITY ISSUES

### Issue #9: UI ACCESSIBILITY — Missing ARIA Labels + Keyboard Navigation

**File**: `frontend/src/components/FindingsTable.jsx` (line 120+)  
**Severity**: 🟡 MEDIUM  
**Category**: Accessibility

**Problems**:
1. Form inputs missing name attributes for screen readers
2. No keyboard navigation (Tab doesn't traverse form properly)
3. No aria-describedby linking error messages to inputs
4. Select dropdowns hard to navigate on mobile
5. Color-only feedback (no icon/text for confidence "90%")

**Minimal Accessibility Fixes**:
```jsx
<input
  type="text"
  name={`pseudonym-${finding.finding_id}`}  // ✅ Add name
  value={decisions[finding.finding_id]?.custom_pseudonym || ''}
  onChange={(e) => handleCustomPseudonymChange(finding.finding_id, e.target.value)}
  aria-label={`Custom pseudonym for ${finding.entity_type}: ${finding.original_value}`}  // ✅ Add aria-label
  aria-describedby={`error-${finding.finding_id}`}  // ✅ Link to errors
  className="..."
/>
<span id={`error-${finding.finding_id}`} role="alert" className="text-red-600">
  {/* Error message if validation failed */}
</span>
```

---

### Issue #10: VISUAL BUG — Batch ID Truncation Inconsistent

**File**: `frontend/src/components/Results.jsx` (line 52)  
**Severity**: 🟡 MEDIUM  
**Category**: UX / Consistency

**Problem**:
```jsx
<code className="bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded text-xs">
  {batch.batch_id.slice(0, 12)}...
</code>
```

**Issue**: Batch IDs are UUIDs (36 chars). Showing first 12 chars might show:
- Full UUID: `353903d9-3182-4ee0-aa50-4e6f0acb692d`
- Truncated: `353903d9-318` (cuts at poor position)
- User can't distinguish batches by visible part

**Fix**:
```jsx
// Show first + last segments for better distinction
<code className="font-mono text-xs bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded">
  {batch.batch_id.slice(0, 8)}...{batch.batch_id.slice(-8)}
</code>
// Output: "353903d9...4e6f0acb692d" (more recognizable)
```

---

### Issue #11: MISSING VALIDATION — File Size Check Before Upload

**File**: `frontend/src/components/Scanner.jsx` (line 32-42)  
**Severity**: 🟡 MEDIUM  
**Category**: UX / Performance

**Problem**:
```jsx
const handleFileScan = async (e) => {
    e.preventDefault()
    if (!uploadedFile) {
      showToast('Seleziona un file', 'warning')
      return
    }

    // ❌ NO SIZE CHECK! User uploads 500MB file
    // Frontend hangs for 30 seconds during upload
    // Then backend rejects with "file too large"
    // UX nightmare

    try {
      const formData = new FormData()
      formData.append('files', uploadedFile)
      
      const response = await axios.post('/api/batches', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
```

**Fix**:
```jsx
const handleFileScan = async (e) => {
    e.preventDefault()
    if (!uploadedFile) {
      showToast('Seleziona un file', 'warning')
      return
    }
    
    // ✅ ADD SIZE CHECK
    const MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  // 100MB
    if (uploadedFile.size > MAX_FILE_SIZE_BYTES) {
      showToast(
        `File troppo grande: ${(uploadedFile.size / 1024 / 1024).toFixed(1)}MB ` +
        `(max ${MAX_FILE_SIZE_BYTES / 1024 / 1024}MB)`,
        'error'
      )
      return
    }
    
    // ✅ SHOW PROGRESS
    try {
      const formData = new FormData()
      formData.append('files', uploadedFile)
      
      const response = await axios.post('/api/batches', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const percentComplete = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          )
          // Update UI: <ProgressBar value={percentComplete} />
        },
      })
```

---

### Issue #12: EDGE CASE — Empty Findings List Handling

**File**: `frontend/src/components/FindingsTable.jsx` (line 100+)  
**Severity**: 🟡 MEDIUM  
**Category**: UX

**Problem**:
```jsx
// If batch.findings is empty:
{batch.findings.map((finding) => (
  <tr key={finding.finding_id} className="...">
    {/* renders nothing */}
  </tr>
))}
// Table shows empty <tbody> → confusing
```

**Fix**:
```jsx
{batch.findings.length === 0 ? (
  <tbody>
    <tr>
      <td colSpan="6" className="px-4 py-8 text-center text-slate-500">
        Nessuna entità trovata nel testo.
      </td>
    </tr>
  </tbody>
) : (
  <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
    {batch.findings.map((finding) => ( /* ... */ ))}
  </tbody>
)}
```

---

### Issue #13: PERFORMANCE — Unnecessary Re-renders in App.jsx

**File**: `frontend/src/App.jsx` (full component)  
**Severity**: 🟡 MEDIUM  
**Category**: Performance / React

**Problem**: No React.memo on child components, no useMemo for expensive computations

```jsx
// Every render of App triggers ALL children to re-render
<FindingsTable batch={batch} onApply={onApply} isLoading={isLoading} />
<Results batch={batch} pseudonymizedText={pseudonymizedText} ... />
<RevertPanel ... />
```

**Fix**:
```jsx
// Wrap components with React.memo
const MemoizedFindingsTable = React.memo(FindingsTable)
const MemoizedResults = React.memo(Results)

// Use in render:
<MemoizedFindingsTable batch={batch} onApply={onApply} isLoading={isLoading} />
<MemoizedResults batch={batch} pseudonymizedText={pseudonymizedText} ... />
```

---

### Issue #14: MISSING TIMEOUT HANDLING — Text Scan No Timeout

**File**: `frontend/src/components/Scanner.jsx`  
**Severity**: 🟡 MEDIUM  
**Category**: UX / Error Handling

**Problem**: No timeout on POST /api/console/scan, if server hangs:
- User waits forever
- No visual feedback
- Unclear if still loading or stuck

**Fix**:
```jsx
const handleTextScan = async (e) => {
    // ... validation ...
    
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 30000)  // 30s timeout
    
    try {
      const response = await axios.post(
        '/api/console/scan',
        { text },
        { signal: controller.signal }
      )
      // ...
    } catch (error) {
      if (error.code === 'ECONNABORTED') {
        showToast('Scan timeout dopo 30 secondi', 'error')
      } else {
        showToast(error.response?.data?.detail || 'Errore', 'error')
      }
    } finally {
      clearTimeout(timeoutId)
    }
  }
```

---

### Issue #15: TYPE SAFETY — Missing TypeScript Interfaces

**File**: `frontend/src/**/*.jsx`  
**Severity**: 🟡 MEDIUM  
**Category**: Code Quality / Maintainability

**Problem**: Using untyped objects throughout frontend

```jsx
// No type safety:
const batch = { /* what properties? */ }
const decision = { action, custom_pseudonym }  // What types?
```

**Fix**: Create TypeScript interfaces (or JSDoc comments for JS):
```javascript
/**
 * @typedef {Object} Finding
 * @property {string} finding_id
 * @property {string} entity_type
 * @property {string} original_value
 * @property {string} proposed_pseudonym
 * @property {number} confidence_score
 * @property {string} detector_name
 * @property {string} [modified_pseudonym]
 * @property {string} review_action
 */

/**
 * @typedef {Object} Batch
 * @property {string} batch_id
 * @property {Finding[]} findings
 * @property {string} safety_label
 * @property {boolean} is_text_input
 * @property {string} [source_text]
 */

/**
 * @param {Batch} batch
 * @param {Function} onApply
 * @param {boolean} isLoading
 */
const FindingsTable = ({ batch, onApply, isLoading }) => {
```

---

## 🟢 LOW SEVERITY ISSUES (Polish/Optimization)

### Issue #16: Console Warnings — Unused Variables

**File**: `backend/app/api/batches_routes.py` (line 54)  
**Fix**: Remove/use `_batch_start_times` properly:
```python
# Currently defined but rarely used
_batch_start_times: dict = {}

# Should track timing for performance metrics:
if batch_id in _batch_start_times:
    elapsed = (datetime.now(timezone.utc) - _batch_start_times[batch_id]).total_seconds()
    logger.info("Batch %s completed in %.2fs", batch_id, elapsed)
```

---

### Issue #17: Missing DEFAULT on Form Fields

**File**: `frontend/src/components/Scanner.jsx`  
**Issue**: No default mode selection, user must select dropdown:
```jsx
// Missing initial value
<select value={mode} onChange={...} >
  <option value="light">Light</option>
  <option value="strict">Strict</option>
</select>
```

**Fix**:
```jsx
const [mode, setMode] = useState('strict')  // Default to strict
const [preset, setPreset] = useState('SOC_LOGS')
```

---

### Issue #18: LOG SANITIZATION INCOMPLETE

**File**: `backend/app/api/auth_routes.py` (line 30-50)  
**Issue**: `_scrub_sensitive` doesn't remove:
- File paths (contain /home/admin/...)
- UUID patterns (might infer batch status)
- Timestamps (timing attacks)

**Enhancement** (not critical):
```python
def _scrub_sensitive(value: Any) -> Any:
    if isinstance(value, str):
        # Remove paths
        value = re.sub(r'/home/\S+', '/home/***', value)
        # Remove full UUIDs (show first 8 chars only)
        value = re.sub(r'\b[a-f0-9]{8}-[a-f0-9]{4}', 'xxxx-xxxx', value)
    # ... rest of scrubbing
```

---

### Issue #19: Docker Build Cache Optimization

**File**: `Dockerfile`  
**Issue**: Frontend dependencies installed but might be cached invalidated:
```dockerfile
# GOOD: Layer caching optimized
COPY frontend/package*.json ./
RUN npm install
COPY frontend/src ./src  # ← This layer change invalidates npm install cache
```

**Fix** (minor):
```dockerfile
# Better: Lock package versions in package-lock.json for consistency
RUN npm ci --only=production  # ci = clean install, respects lock file
```

---

### Issue #20: Missing Rate Limit Headers

**File**: `backend/app/core/rate_limit.py`  
**Enhancement**: Add HTTP headers to responses:
```python
# When rate limited, include:
X-RateLimit-Limit: 50
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1646087400  # Unix timestamp when limit resets

# Helps clients throttle automatically
```

---

## 📊 QUICK ISSUE SUMMARY

| # | Title | Severity | Type | Fix Effort |
|---|-------|----------|------|-----------|
| 1 | Race condition in batch_manager | 🔴 CRITICAL | Concurrency | 1-2 hours |
| 2 | Finding deduplication bug | 🔴 CRITICAL | Logic | 30 mins |
| 3 | FindingsTable React state sync | 🔴 CRITICAL | React | 15 mins |
| 4 | Missing input validation | 🟠 HIGH | Validation | 30 mins |
| 5 | Incomplete error handling (rollback) | 🟠 HIGH | Error Handling | 1-2 hours |
| 6 | Silent failure in Scanner | 🟠 HIGH | UX | 20 mins |
| 7 | Passphrase validation missing | 🟠 HIGH | Data Integrity | 15 mins |
| 8 | No unique constraint on finding_id | 🟠 HIGH | Data Integrity | 45 mins |
| 9 | Accessibility missing (ARIA) | 🟡 MEDIUM | A11y | 1 hour |
| 10 | Batch ID truncation UX | 🟡 MEDIUM | UI | 10 mins |
| 11 | No file size preview check | 🟡 MEDIUM | UX | 20 mins |
| 12 | Empty findings list handling | 🟡 MEDIUM | UX | 15 mins |
| 13 | Unnecessary re-renders | 🟡 MEDIUM | Performance | 30 mins |
| 14 | Missing timeout handling | 🟡 MEDIUM | UX | 20 mins |
| 15 | Type safety (JSDoc/TS) | 🟡 MEDIUM | Quality | 2-3 hours |
| 16-20 | Polish & optimization | 🟢 LOW | Various | <30 mins each |

---

## 🎯 RECOMMENDED FIX PRIORITY (By Business Impact)

**Phase 1 (IMMEDIATE - Before Production):**
1. ✅ **Issue #1** — Race condition (can corrupt data)
2. ✅ **Issue #2** — Finding duplication (UX confusion)
3. ✅ **Issue #3** — React state sync (crashes review flow)
4. ✅ **Issue #7** — Passphrase validation (data loss)

**Phase 2 (Next Release):**
5. ✅ **Issue #4** — Input validation
6. ✅ **Issue #5** — Error handling/rollback
7. ✅ **Issue #8** — unique constraint

**Phase 3 (Polish):**
8. ✅ **Issues #6, 9-15** — UX improvements

---

## 💾 ESTIMATED TIME to Fix All

- **Phase 1 (Critical)**: 3-4 hours
- **Phase 2 (High)**: 4-5 hours  
- **Phase 3 (Medium/Low)**: 6-8 hours

**Total**: ~13-17 hours for complete remediation

