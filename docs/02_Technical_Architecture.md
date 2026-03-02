# Architettura Tecnica — Local Pseudonymization Tool

**Autore:** Team Engineering
**Versione:** 4.0.4
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
    image: pseudonym-tool:4.0.4
    ports: ["80:80"]  # Static React build
  
  backend:
    image: pseudonym-tool:4.0.4
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
make test             # Run pytest (179 tests, 58.76% coverage)
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

## 6. Testing Strategy

**Test Coverage: 58.76% (179 tests)**

Critical modules:
- `auth.py`: 91.67% coverage → Session management
- `crypto.py`: 94.92% coverage → AES-256-GCM encryption
- `schemas.py`: 96.48% coverage → Request validation
- `batch_manager.py`: 64.67% coverage → Lifecycle + TOCTOU fixes

Test categories:
- Unit tests: 120+
- Integration tests: 45+
- Stress tests: Concurrent 10-thread batch processing
- Regression tests: 11 critical bug fixes (race conditions, memory leaks)

Run: `make test` or `pytest backend/tests/ -v --cov`

---

## 7. Infrastructure (Container Only)

**Base Image:** `python:3.12.3-slim`
**Frontend Build:** Multi-stage (Node 18 → Vite build → nginx static serve)
**Backend:** Uvicorn on port 8000
**Storage:** /tmp/pseudonymizer (ephemeral)
**Volumes:**
- `/app/config/` (dictionaries)
- `/tmp/pseudonymizer/` (batch data)

---

**Last Updated:** 2026-03-02  
**Version History:** 1.0 (MVP, 2026-02-25) → 4.0.4 (current, 2026-03-02)
