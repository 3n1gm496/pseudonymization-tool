# Architettura Tecnica — Local Pseudonymization Tool

**Autore:** Team Engineering
**Versione:** 5.0.0
**Data:** 2026-03-02

---

## 1. Panoramica dell'Architettura

L'applicazione è una **single-page web application (SPA)** con architettura completamenz locale e offline. Sistema client-server con separazione chiara tra:

- **Frontend:** React 18 + Vite (SPA)
- **Backend:** FastAPI (Python 3.12) con Uvicorn
- **Processing:** Moduli Python ortogonali (parsing, detection, pseudonimizzazione, revert)

```
┌─────────────────────────────────────────────────────────┐
│          React 18 + Vite (Frontend SPA)                 │
│  ┌──────────┬──────────┬──────────┬──────────────────┐  │
│  │ Scanner  │ Review   │ Results  │ RevertPanel      │  │
│  │ (S3)     │ (S2)     │ (S3)     │ (Optional)       │  │
│  └──────────┴──────────┴──────────┴──────────────────┘  │
│                        ▼ (fetch API)                    │
├─────────────────────────────────────────────────────────┤
│   FastAPI (Python 3.12.3) - Server ASGI                 │
│  ┌──────────┬─────────┬─────────┬──────────────────┐   │
│  │ Auth     │ Batch   │ Findings│ Revert           │   │
│  │ Routes   │ Routes  │ Routes  │ Routes           │   │
│  └──────────┴─────────┴─────────┴──────────────────┘   │
│                   ▼ orchestration                        │
├─────────────────────────────────────────────────────────┤
│   Processing Pipeline (Modular Design)                  │
│  ┌──────────┬──────────┬──────────┬──────────────────┐  │
│  │ Parser   │ Detector │ Pseudo.  │ Mapping & Report │  │
│  │ Module   │ Module   │ Module   │ Module           │  │
│  └──────────┴──────────┴──────────┴──────────────────┘  │
│                        ▼                                │
│   Filesystem: /tmp/pseudonymizer/{batch_id}/            │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Componenti Dettagliati

### 2.1. Frontend (React 18 + Vite)

**Stack:**
- Framework: `React 18.2.0`
- Build Tool: `Vite` (tree-shaking, fast HMR)
- Styling: `Tailwind CSS 3.3`
- HTTP: `fetch` API standard

**Architettura Componenti:**

1. **Scanner (Fase 1 - SCAN)**
   - Upload file (drag & drop)
   - Policy selection (Light/Strict/Custom)
   - Passphrase input
   - Avvio scansione → Batch ID

2. **FindingsTable (Fase 2 - REVIEW)**
   - Entità trovate (table paginated)
   - Pseudonimo proposto per entity
   - Azioni: accetta/modifica/escudi per finding
   - Real-time pseudonym editing

3. **Results (Fase 3 - RESULTS)**
   - Summary: file, entità, tempo
   - **Passphrase visibile** (con copy button + show/hide)
   - **mapping.enc downloadable** (direct from Results)
   - Output ZIP download
   - Prepare for AI section (encrypted mapping generation)

4. **RevertPanel (Fase 4 - OPTIONAL)**
   - **Tab 1: Decifra Risposta AI** - Decrypt AI responses using passphrase
   - **Tab 2: Revert Batch ZIP** - Full batch reversal (original + mapping)
   - Accessible after Results phase

**Comunicazione:**
- All API calls via REST fetch to `127.0.0.1:8000`
- Request/response validation with schemas
- Error handling + user-friendly messages

### 2.2. Backend (FastAPI + Uvicorn)

**Stack:**
- Runtime: `Python 3.12.3`
- Framework: `FastAPI 0.110+`
- Server: `Uvicorn` (ASGI)
- Binding: `127.0.0.1:8000` (loopback only)

**API Routes:**

```
Health & Status
├─ GET  /health              → Health check
├─ GET  /ready               → Readiness check

Batch Management
├─ POST   /api/batches                          → Create batch, upload files
├─ GET    /api/batches/{batch_id}               → Get batch metadata
├─ POST   /api/batches/{batch_id}/scan          → Start scan pipeline
├─ GET    /api/batches/{batch_id}/findings      → Get detected entities
├─ POST   /api/batches/{batch_id}/review        → Submit review decisions
├─ POST   /api/batches/{batch_id}/apply         → Apply pseudonymization
├─ GET    /api/batches/{batch_id}/download      → Download results ZIP
├─ DELETE /api/batches/{batch_id}               → Clean batch

Mapping Management (v4.0.4+)
├─ GET    /api/batches/{batch_id}/mapping       → Get encrypted mapping
├─ POST   /api/batches/{batch_id}/decipher      → Decrypt mapping with passphrase

Revert Operations (v4.0.4+)
├─ POST   /api/batches/{batch_id}/revert/text   → Revert single text finding
├─ POST   /api/batches/{batch_id}/revert/batch  → Revert full batch ZIP

Policy Management
├─ GET    /api/policies                         → List policies
├─ GET    /api/policies/{policy_id}/preview     → Preview policy config
```

**Gestione Stato Batch:**
- Stored in `/tmp/pseudonymizer/{batch_id}/`
- Lifecycle: `created` → `scanned` → `reviewed` → `applied`
- Cleanup: Auto-delete after 24h or manual DELETE

### 2.3. Processing Pipeline

5 moduli sequenziali, ortogonali e testabili:

#### 1. Parser Module (`parsers/`)
```
Input: File (docx, pdf, xlsx, txt, png, jpg)
       ↓
[Estensione Check] → [Parser Factory]
       ↓
Parsers:
├─ text_parser.py   → .txt files (readlines)
├─ docx_parser.py   → .docx (python-docx)
├─ pdf_parser.py    → .pdf (pypdf)
├─ xlsx_parser.py   → .xlsx (openpyxl)
├─ image_parser.py  → .png/.jpg (Pillow + Tesseract OCR)
       ↓
Output: {
  "file_name": "doc.pdf",
  "text": "Mario Rossi...",
  "metadata": {"pages": 5, "parsed_at": "2026-03-02T10:30:00Z"}
}
```

#### 2. Detector Module (`detectors/`)
```
Input: Parsed text
       ↓
[Detector Pipeline]
├─ regex_detectors.py
│  ├─ Email: user@domain.it
│  ├─ IP: 192.168.1.1
│  ├─ CF: RSSMRA80A01H501T (16 char)
│  ├─ P.IVA: 12345678901
│  └─ URL: https://example.com
│
├─ dictionary_detector.py
│  ├─ person_names.txt (1000+ nomi)
│  ├─ project_codes.txt
│  └─ hostnames.txt
│
└─ [Optional] engine.py (NER - reserved)
       ↓
Output: [
  Finding(
    value="mario.rossi@ente.gov.it",
    finding_type="EMAIL",
    position={"file": "doc.pdf", "line": 5, "char": 12},
    confidence=0.95,
    context="Dear mario.rossi@ente.gov.it, ..."
  ),
  ...
]
```

#### 3. Pseudonymizer Module (`pseudonymizer/`)
```
Input: Findings + Mode (Light/Strict)
       ↓
transformer.py:
├─ Email    → user_{rand_id}@orgdom_{rand_id}.gov.it
├─ IP       → {rand_octet}.{rand_octet}.{rand_octet}.{rand_octet}
├─ CF       → Random 16-char XXXXXXXXXXX...
├─ P.IVA    → Random 11-digit
├─ Name     → Name_{rand_id}
└─ Generic  → ENTITY_{rand_id}
       ↓
Output: Mapping {
  "mario.rossi@ente.gov.it": "user_3847@orgdom_5621.gov.it",
  "192.168.1.1": "10.42.137.88",
  ...
}
Consistency: All occurrences of same value → same pseudonym within batch
```

#### 4. Review & Transform Module (`pseudonymizer/engine.py`)
```
Input: Findings + User Review Decisions + Mapping
       ↓
For each finding:
├─ ACCEPTED → Use proposed pseudonym
├─ MODIFIED → Use user-provided pseudonym
└─ SKIPPED  → Keep original value
       ↓
Apply string replacements in files
       ↓
Output: Pseudonymized files (*.pseudonymized.ext)
```

#### 5. Mapping & Report Module (`report/`)
```
Input: Final mapping, findings metadata
       ↓
generator.py:
├─ mapping.json (clear) → {original: pseudonym}
│
├─ mapping.enc:
│  ├─ Read passphrase from session
│  ├─ AES-256-GCM encryption (cryptography lib)
│  ├─ Store in BASE64
│  └─ File: mapping.enc (can be downloaded from Results)
│
├─ report.json (statistics)
│  ├─ Files processed: N
│  ├─ Entities found: M
│  ├─ Execution time
│  └─ Batch UUID
│
└─ report.html (human-readable summary)
       ↓
Output: All files packaged in results_{batch_id}.zip
```

### 2.4. Security & Isolation (v4.0.4)

**Network:**
- ✅ Binding: `127.0.0.1:8000` only (no external access)
- ✅ No outbound calls (verified by unit tests)
- ✅ Session management: JWT-like tokens (stored in session store)

**Encryption:**
- passphrase → AES-256-GCM via `cryptography` library
- Symmetric encryption (no private keys needed)
- User supplies passphrase → Session key → mapping.enc encrypted

**File Safety:**
- Temp storage: `/tmp/pseudonymizer/{batch_id}/`
- Auto-cleanup: DELETE batch after 24h (configurable)
- No sensitive data in logs (only metadata)
- Output: ZIP with no original files (only pseudonymized + report + encrypted mapping)

**Revert Flows (v4.0.4+):**
- **Text Revert:** Single finding → Original value using passphrase
- **Batch Revert:** Full ZIP reversal (recreate original using mapping.enc + passphrase)

---

## 3. Data Model

### Batch
```python
{
  "batch_id": "uuid-1234",
  "created_at": "2026-03-02T10:15:00Z",
  "status": "applied",  # created|scanned|reviewed|applied
  "policy_id": "LIGHT",
  "passphrase": "<hashed>",
  "file_count": 5,
  "findings": [...],
  "mapping": {...},
  "expires_at": "2026-03-03T10:15:00Z"  # 24h TTL
}
```

### Finding
```python
{
  "id": "finding-uuid",
  "value": "mario.rossi@ente.gov.it",
  "finding_type": "EMAIL",
  "file": "document.pdf",
  "position": {"page": 1, "char": 42},
  "confidence": 0.95,
  "context": "Dear mario.rossi@ente.gov.it, ...",
  "pseudonym": "user_3847@orgdom_5621.gov.it",  # proposed
  "status": "accepted"  # accepted|modified|skipped
}
```

---

## 4. Deployment Architecture

**Deployment Methods:**

### 4.1. Docker (Production)
```yaml
# docker-compose.yml
services:
  frontend:
    image: pseudonym-tool:5.0.0
    ports: ["80:80"]  # Static React build
  
  backend:
    image: pseudonym-tool:5.0.0
    ports: ["127.0.0.1:8000:8000"]  # API
    volumes:
      - /tmp/pseudonymizer:/tmp/pseudonymizer
      - ./config:/app/config
```

**Makefile targets:**
```bash
make build-docker     # Build multi-stage image
make start            # Start docker-compose
make dev              # Dev mode with hot reload
make test             # Run pytest (267 tests, 64% coverage)
make clean            # Remove containers + temp data
```

### 4.2. Local Installation (Air-gapped)
```bash
./prepare_offline.sh      # Download wheels to ./wheelhouse
./start.sh               # Create venv, install, run

# On target machine (no internet):
python -m venv venv
pip install --no-index --find-links ./wheelhouse -r requirements.txt
python backend/app/main.py
```

---

## 5. Performance & Scalability (v4.0.4)

**Limits (by design):**
- Max file size: 50MB per file (configurable)
- Max batch size: 500 files (configurable)
- Concurrent batches: Limited by system RAM (~20-30 on 4GB system)
- Batch TTL: 24h (auto-cleanup)

**Optimizations:**
- Rate limiting: 100 req/min per client (configurable)
- Batch cleanup: Async background task
- File streaming: Large PDF/XLSX handled with streaming parser
- Mapping cache: In-memory during batch lifecycle

---

## 5.1. Phase 4: Async Architecture (Celery + Redis)

### 🎯 Obiettivo

Garantire elaborazione asincrona e scalabile per scan di lunga durata, evitando timeout HTTP e consentendo processamento parallelo di batch multipli.

### 🏗️ Architettura Componenti

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                            │
│   POST /api/batches → 202 Accepted + task_id                       │
│   GET /api/batches/{id}/status → {status, progress, result}        │
└────────────────────────┬────────────────────────────────────────────┘
                         │ HTTP REST
┌────────────────────────▼────────────────────────────────────────────┐
│                      FastAPI Backend                                │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  API Routes (batches_routes.py)                             │   │
│  │  - POST /api/batches → create_batch_api()                   │   │
│  │    ├─ Create batch metadata                                 │   │
│  │    ├─ Enqueue task: run_scan_pipeline.delay(batch_id)       │   │
│  │    └─ Return 202 + task_id                                  │   │
│  │                                                              │   │
│  │  - GET /api/batches/{id}/status → get_batch_status_api()    │   │
│  │    ├─ Check Celery task state (PENDING/STARTED/SUCCESS)     │   │
│  │    ├─ Get progress from Redis (if available)                │   │
│  │    └─ Return {status, progress, result}                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                         │                                           │
│                         │ enqueue/query                             │
│                         ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │         Celery Task Module (task.py)                        │   │
│  │  @celery_app.task(bind=True, name="run_scan_pipeline")      │   │
│  │                                                              │   │
│  │  - Task execution:                                           │   │
│  │    1. Update state: STARTED                                  │   │
│  │    2. Execute scan_pipeline()                                │   │
│  │    3. Update progress (Redis: batch:{id}:progress)           │   │
│  │    4. Return result / raise error                            │   │
│  │                                                              │   │
│  │  - Error handling: Automatic retries (3x with exp backoff)  │   │
│  │  - Timeouts: Soft limit 55min, Hard limit 60min             │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────────────┘
                         │ publish/consume
┌────────────────────────▼────────────────────────────────────────────┐
│                       Redis (Broker + Backend)                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Task Queue       │  │ Task Results      │  │ Progress Cache   │  │
│  │ (celery)         │  │ (celery-task-     │  │ (batch:{id}:*)   │  │
│  │                  │  │  meta-{task_id})  │  │                  │  │
│  │ - Pending tasks  │  │ - State: PENDING  │  │ - Progress: 45%  │  │
│  │ - Priority queue │  │ - Result payload  │  │ - Error details  │  │
│  │ - Routing keys   │  │ - Exception info  │  │ - Timestamps     │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                         │ consume
┌────────────────────────▼────────────────────────────────────────────┐
│               Celery Worker (celery-worker container)               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Worker Pool (--concurrency=4)                              │   │
│  │  ├─ Worker 1: Processing batch_abc123                       │   │
│  │  ├─ Worker 2: Idle                                           │   │
│  │  ├─ Worker 3: Processing batch_def456                       │   │
│  │  └─ Worker 4: Idle                                           │   │
│  │                                                              │   │
│  │  Features:                                                   │   │
│  │  - Autoscaling: min=2, max=8 workers                        │   │
│  │  - Graceful shutdown: SIGTERM handling                      │   │
│  │  - Task prefetch: 1 task per worker (fair distribution)     │   │
│  │  - Max tasks per child: 100 (memory leak prevention)        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 📋 Task Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│  1. PENDING                                                     │
│     Task created, waiting in queue                              │
│     Frontend: "Scan in coda..."                                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Worker picks up task
┌──────────────────────▼──────────────────────────────────────────┐
│  2. STARTED                                                     │
│     Worker executing run_scan_pipeline()                        │
│     Frontend: "Scansione in corso... 0%"                        │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Progress updates (optional)
┌──────────────────────▼──────────────────────────────────────────┐
│  3. PROGRESS (optional, via Redis)                             │
│     self.update_state(..., meta={'progress': 45})               │
│     Frontend: Polling /status → "Scansione in corso... 45%"    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Task completes successfully
┌──────────────────────▼──────────────────────────────────────────┐
│  4. SUCCESS                                                     │
│     Result stored in Redis: celery-task-meta-{task_id}          │
│     Frontend: "Scansione completata!" + Show findings           │
│     Data: {status: "success", findings_count: 42, ...}          │
└─────────────────────────────────────────────────────────────────┘
                       OR (error case)
┌─────────────────────────────────────────────────────────────────┐
│  4. FAILURE                                                     │
│     Exception stored in Redis with traceback                    │
│     Frontend: "Errore durante la scansione: {error_msg}"       │
│     Data: {status: "failure", error: "FileNotFoundError..."} │
└─────────────────────────────────────────────────────────────────┘
```

### 🔌 API Patterns (202 Accepted)

**Endpoint Asincrono:**
```python
# POST /api/batches
@router.post("/batches", status_code=202)
async def create_batch_api(request: BatchCreateRequest):
    # 1. Create batch metadata
    batch = batch_manager.create_batch(...)
    
    # 2. Enqueue async task
    task = run_scan_pipeline.delay(batch.id)
    
    # 3. Store task_id in batch record
    batch.task_id = task.id
    batch_manager.update_batch(batch)
    
    # 4. Return 202 Accepted
    return {
        "batch_id": batch.id,
        "task_id": task.id,
        "status": "pending",
        "message": "Scan enqueued, poll /api/batches/{id}/status"
    }
```

**Polling Endpoint:**
```python
# GET /api/batches/{batch_id}/status
@router.get("/batches/{batch_id}/status")
async def get_batch_status_api(batch_id: str):
    batch = batch_manager.get_batch(batch_id)
    task_result = AsyncResult(batch.task_id, app=celery_app)
    
    # Check task state
    if task_result.state == "PENDING":
        return {"status": "pending", "progress": 0}
    elif task_result.state == "STARTED":
        return {"status": "running", "progress": task_result.info.get("progress", 0)}
    elif task_result.state == "SUCCESS":
        return {"status": "completed", "result": task_result.result}
    elif task_result.state == "FAILURE":
        return {"status": "failed", "error": str(task_result.info)}
```

### 🚀 Deployment Modes

#### Mode 1: Docker Compose (Production)

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - redis
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
  
  celery-worker:
    build: ./backend
    command: celery -A app.core.tasks worker --loglevel=info --concurrency=4
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - redis
```

**Scaling Workers:**
```bash
docker compose up -d --scale celery-worker=4
```

#### Mode 2: Development (Eager Mode)

```bash
# .env
CELERY_TASK_ALWAYS_EAGER=true
CELERY_TASK_EAGER_PROPAGATES=true

# Task runs synchronously in FastAPI process (no broker needed)
```

#### Mode 3: Production (Kubernetes)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: worker
        image: pseudonymizer-backend:latest
        command: ["celery", "-A", "app.core.tasks", "worker"]
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

### 📊 Monitoring (Flower - Optional)

```bash
# Start Flower web UI
celery -A app.core.tasks flower --port=5555

# Access: http://localhost:5555
# Features:
# - Task history and status
# - Worker statistics
# - Task retry/cancel controls
# - Real-time metrics
```

### 🔧 Configuration Parameters

**Celery Settings (backend/app/core/config.py):**
```python
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Task settings
CELERY_TASK_TIME_LIMIT = 3600  # 1 hour hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 3300  # 55 min soft limit
CELERY_TASK_ACKS_LATE = True  # Acknowledge after completion (not before)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair task distribution

# Result settings
CELERY_RESULT_EXPIRES = 86400  # 24 hours
CELERY_TASK_TRACK_STARTED = True  # Enable STARTED state tracking

# Error handling
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_DEFAULT_RETRY_DELAY = 60  # 1 minute
```

**Redis Fallback (Storage):**
```python
# If Redis unavailable, fallback to in-memory dict
try:
    redis_client = redis.Redis.from_url(REDIS_URL)
    redis_client.ping()
except:
    logger.warning("Redis unavailable, using in-memory storage")
    storage = {}  # Simple dict fallback
```

### ✅ Testing Infrastructure

**Test Configuration (tests/conftest.py):**
```python
@pytest.fixture(autouse=True)
def setup_celery_for_testing():
    """Enable Celery EAGER mode for synchronous test execution"""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False

@pytest.fixture(autouse=True)
def mock_redis_for_tests():
    """Mock Redis to trigger fallback to in-memory storage"""
    os.environ["REDIS_URL"] = "redis://invalid-redis-host:6379/0"
    yield
    os.environ.pop("REDIS_URL", None)
```

**Test Results (Phase 4):**
- 64 critical tests verified ✅
- 0 regressions ✅
- API contract tests updated for 202 Accepted pattern ✅

### 🎯 Benefits

1. **No HTTP Timeouts**: Long scans (30+ min) don't timeout
2. **Scalability**: Horizontal scaling via multiple workers
3. **Resilience**: Task retries on transient failures
4. **Monitoring**: Real-time task status and progress
5. **Resource Efficiency**: Workers auto-restart after 100 tasks (memory leak prevention)
6. **Graceful Degradation**: Redis fallback to in-memory storage

---

## 6. Testing Strategy

**Test Coverage: 64% (v5.0.0 Verified)**

**v5.0.0 Test Suite (267 passing, 12 skipped):**
- `test_api_contract.py`: 9/9 PASS — API contracts including 202 Accepted pattern
- `test_additional_fixes.py`: 11/11 PASS — Cleanup, logging, lifecycle
- `test_functional.py`: 44/44 PASS — Detectors, parsers, security, crypto

**Module Coverage:**
- `auth.py`: 95.10% coverage → Session management + JWT
- `crypto.py`: 94.92% coverage → AES-256-GCM encryption
- `schemas.py`: 96.48% coverage → Request validation
- `batch_manager.py`: 64.67% coverage → Lifecycle + TOCTOU fixes
- `pipeline.py`: 65%+ coverage (CI threshold)

**Test Infrastructure:**
- Celery EAGER mode: Tasks run synchronously in tests (no broker)
- Redis mocking: Invalid URL triggers fallback to in-memory storage
- 202 Accepted pattern validation: All async endpoints tested
- Zero regressions: Complete backward compatibility verified

**Test Categories:**
- Unit tests: 120+
- Integration tests: 45+
- Async tests: 9 (API contract, task lifecycle)
- Stress tests: Concurrent 10-thread batch processing
- Regression tests: 11 critical bug fixes (race conditions, memory leaks)

Run: `make test` or `pytest backend/tests/ -v --cov`

**Test Results:** 267 passing, 12 skipped, 0 failed (CI verified)

---

## 7. Infrastructure (Container + Phase 4)

**Base Image:** `python:3.12.3-slim`
**Frontend Build:** Multi-stage (Node 18 → Vite build → nginx static serve)
**Backend:** Uvicorn on port 8000
**Storage:** /tmp/pseudonymizer (ephemeral)

**Phase 4 Components:**
- **Redis**: `redis:7-alpine` (message broker + result backend)
- **Celery Worker**: Python 3.12 + Celery 5.3+
- **Networking**: Internal Docker network, no external exposure

**Volumes:**
- `/app/config/` (dictionaries)
- `/tmp/pseudonymizer/` (batch data)

---

**Last Updated:** 2026-03-02  
**Version History:**  
- 1.0 (MVP, 2026-02-25): Initial release with sync processing
- 5.0.0 (2026-03-03): Security hardening, CI hardening, code quality (PR #1-#10), dark mode, readiness API  
- 4.1.0 (Phase 4): Async architecture with Celery + Redis, 202 Accepted pattern, scalable workers
- 5.0.0 (2026-03-03): Security hardening (13 CVE fixed), Docker hardening, Redis auth, CI hardening, 72 unused imports removed

**v5.0.0 Release Date:** 2026-03-03  
**v5.0.0 Test Verification:** 267 tests passing ✅
