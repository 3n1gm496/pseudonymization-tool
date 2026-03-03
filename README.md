# Local Pseudonymization Tool v5.0.0

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![React 18.2](https://img.shields.io/badge/React-18.2-61dafb.svg)](https://react.dev)
[![FastAPI 0.110](https://img.shields.io/badge/FastAPI-0.110-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 348 passing](https://img.shields.io/badge/Tests-348%20passing-brightgreen.svg)](backend/tests/)
[![Coverage: 71%](https://img.shields.io/badge/Coverage-71%25-yellowgreen.svg)]()
[![Async: Celery + Redis](https://img.shields.io/badge/Async-Celery%20%2B%20Redis-red.svg)](docs/02_Technical_Architecture.md)

Web application locale moderna per la pseudonimizzazione sicura di dati sensibili in documenti di testo, DOCX, XLSX, PDF e immagini. Interfaccia React con Tailwind CSS, darkmode supportato. Progettato per ambienti enterprise che richiedono massima sicurezza e capacità di operare completamente offline.

🔗 **Repository:** [github.com/3n1gm496/pseudonymization-tool](https://github.com/3n1gm496/pseudonymization-tool)

## ✨ Caratteristiche

- **🔒 100% Offline** — Nessuna chiamata di rete esterna, tutti i dati rimangono sulla macchina locale
- **📄 Multi-formato** — Supporto per TXT, CSV, MD, DOCX, XLSX, PDF (testuali), JPG, PNG
- **🔐 Sicurezza Avanzata** — Mapping cifrato con passphrase AES-256-GCM, zero logging di dati sensibili
- **⚡ Architettura Asincrona** — Elaborazione con Celery + Redis, scalabile e resiliente
- **⚙️ Modalità Flessibili** — `light` (solo entità di rete) e `strict` (tutte le entità PII)
- **🧭 Input Unificato** — testo inline e upload documenti disponibili nello stesso flusso
- **🛡️ Preset Policy** — `SOC Logs`, `Policy Docs`, `Email Headers` con preview entità abilitate
- **👁️ Review Manuale** — Interfaccia per rivedere e approvare/rifiutare ogni pseudonimo proposto
- **📊 Report Dettagliati** — HTML navigabile e JSON strutturato per audit trail
- **✅ Readiness API** — endpoint `/api/ready` per distinguere processo attivo da servizio pronto
- **🎯 Deterministico** — Stesso input = stesso output con la stessa passphrase

---

## 📋 Indice

- [Architettura](#-architettura)
- [Quick Start](#-quick-start)
- [Configurazione](#-configurazione)
- [Utilizzo](#-utilizzo)
- [Integrazione AI](#-integrazione-con-ai)
- [Sicurezza](#-sicurezza-e-limitazioni)
- [Sviluppo](#-sviluppo)
- [Contributing](#-contributing)
- [Licenza](#-licenza)

---

## 🏗️ Architettura

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React 18)                      │
│              UI/UX Layer + Dark Mode + Responsive               │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/REST API
┌────────────────────────────▼────────────────────────────────────┐
│                      Backend (FastAPI)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Auth Module  │  │ API Routes   │  │ Batch Mgr    │           │
│  │ (JWT Auth)   │  │ (/api/*)     │  │ (Lifecycle)  │           │
│  └──────────────┘  └──────────────┘  └──────┬───────┘           │
│                                             │                   │
│  ┌──────────────────────────────────────────▼─────────────────┐ │
│  │                 Celery Task Queue                          │ │
│  │  - Async scan execution (run_scan_pipeline)                │ │
│  │  - Background processing                                   │ │
│  │  - Task status tracking                                    │ │ 
│  └──────────────────────────────────────────┬─────────────────┘ │
│                                             │                   │
│  ┌──────────────┐  ┌──────────────┐   ┌─────▼──────┐            │
│  │ Detectors    │  │ Parsers      │   │ Redis      │            │
│  │ (Regex/Dict/ │  │ (PDF/DOCX/   │   │ (Broker +  │            │
│  │  SOC)        │  │  XLSX/IMG)   │   │  Results)  │            │
│  └──────────────┘  └──────────────┘   └────────────┘            │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Pseudonymizer│  │ Crypto (AES) │  │ Report Gen   │           │
│  │ (Transform)  │  │ (Encryption) │  │ (HTML/JSON)  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Storage & Persistence                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Redis State  │  │ Outputs      │  │ Uploads      │           │
│  │ (Batch/Sess) │  │ (ZIP files)  │  │ (Temp files) │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### Architettura Asincrona (Celery + Redis)

**🎯 Obiettivo:** Elaborazione asincrona per scan di lunga durata, evitando timeout HTTP.

**Componenti:**

1. **Celery Workers**: Processano task in background
   - `run_scan_pipeline`: Task principale per scan completi
   - Scalabilità orizzontale (multiple workers)
   - Graceful shutdown e error handling

2. **Redis**: Message broker e result backend
   - Queue: `celery` (task dispatch)
   - Results: `celery-task-meta-*` (task status/results)

3. **API Pattern (202 Accepted)**:
   ```
   POST /api/batches → 202 Accepted + task_id
   GET /api/batches/{id}/status → {status, progress, result}
   ```

4. **Task Lifecycle**:
   ```
   PENDING → STARTED → SUCCESS/FAILURE
              ↓
          PROGRESS updates (opzionale)
   ```

**🔧 Deployment Modes:**

- **Docker Compose** (raccomandato): All-in-one con Redis + Celery worker
- **Local Dev**: Celery EAGER mode (task sincroni, no Redis)
- **Production**: Multiple workers, Redis cluster, monitoring con Flower

Vedi [docs/02_Technical_Architecture.md](docs/02_Technical_Architecture.md) per dettagli completi.

---

## ⚡ Quick Start

### Metodo 1: Docker (Raccomandato)

**Prerequisiti**: Docker e Docker Compose installati

```bash
# Clone del repository
git clone https://github.com/3n1gm496/pseudonymization-tool.git
cd pseudonymization-tool

# 1. Crea il file .env a partire dall'esempio (OBBLIGATORIO)
touch .env
# Modifica .env e imposta almeno:
#   AUTH_PASSWORD=<password-sicura>
#   REDIS_PASSWORD=<password-redis-sicura>

# 2. Avvio con Docker
make start
```

Oppure manualmente:

```bash
touch .env
# Modifica .env con le tue credenziali
docker compose up --build -d
```

> **Nota:** Il file `.env` contiene credenziali sensibili e non deve mai essere committato. È già incluso nel `.gitignore`.

**Servizi avviati:**
- `backend`: FastAPI app (port 8000)
- `redis`: Message broker (porta interna, non esposta sull'host)
- `celery-worker`: Background task processor

Accedi all'interfaccia: **http://localhost:8000**

**Comandi utili:**
```bash
make logs      # Visualizza i log
make stop      # Ferma il servizio
make health    # Verifica lo stato
```

Vedi [Makefile](Makefile) per tutti i comandi disponibili.

---

### Metodo 2: Installazione Locale (Senza Docker)

**Per ambienti air-gapped o sistemi senza Docker**

Vedi [scripts/legacy/README.md](scripts/legacy/README.md) per istruzioni dettagliate su:
1. Installazione con Python venv
2. Modalità offline (machine senza internet)
3. Preparazione pacchetto wheelhouse
4. Troubleshooting prerequisiti (Python, Tesseract)

**Quick command:**
```bash
make legacy-start
```

---

## ⚙️ Configurazione

### Environment Variables

**Core Backend:**
```bash
# Server
BACKEND_HOST=0.0.0.0                    # Bind address
BACKEND_PORT=8000                       # HTTP port
LOG_LEVEL=info                          # Logging: debug|info|warning|error

# Async Processing
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0  # Message broker (con auth)
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0          # Result backend (con auth)
CELERY_RESULT_BACKEND=${REDIS_URL}                         # Task results storage

# Security
JWT_SECRET_KEY=your-secret-key-change-in-production  # JWT signing key
JWT_ALGORITHM=HS256                     # JWT algorithm
ACCESS_TOKEN_EXPIRE_MINUTES=30          # Token validity

# Storage Paths
UPLOAD_DIR=/app/uploads                 # Temp file uploads
OUTPUT_DIR=/app/outputs                 # Generated reports (ZIP)
PSEUDONYMIZER_STATE_DIR=/app/state  # Runtime writable state (montato come volume Docker)
```

**Celery Worker Configuration:**
```bash
# Worker settings
CELERY_WORKER_CONCURRENCY=4             # Concurrent tasks per worker
CELERY_WORKER_MAX_TASKS_PER_CHILD=100   # Restart after N tasks (memory)
CELERY_TASK_TIME_LIMIT=3600             # Hard timeout (seconds)
CELERY_TASK_SOFT_TIME_LIMIT=3300        # Soft timeout (55 min)

# Queue routing
CELERY_TASK_DEFAULT_QUEUE=celery        # Default queue name
```

**Redis Configuration:**
```bash
# Redis persistence (optional)
REDIS_MAXMEMORY=256mb                   # Memory limit
REDIS_MAXMEMORY_POLICY=allkeys-lru      # Eviction policy
```

**Development Mode:**
```bash
# Disable async for local dev (tasks run synchronously)
CELERY_TASK_ALWAYS_EAGER=true           # Run tasks inline (no broker needed)
CELERY_TASK_EAGER_PROPAGATES=true       # Propagate exceptions in eager mode
```

### Configuration Files

**Backend Policies:**
- `backend/config/policies/*.yaml` - Scan policies (SOC Logs, Email Archive, etc.)
- `backend/config/dictionaries/` - Detection dictionaries (hostnames, names, codes)

**Frontend Settings:**
- `frontend/.env` - API URL configuration (Vite environment)
- `frontend/vite.config.js` - Dev server proxy setup

Vedi [docs/04_Policies.md](docs/04_Policies.md) per dettagli sulle policy di scan.

---

## 💡 Utilizzo

1. **Upload**: Trascina i file da processare nell'area di upload
2. **Configura**: Seleziona la modalità (`light` o `strict`) e inserisci una **passphrase robusta** (essenziale per la sicurezza del mapping).
   - Seleziona il preset policy (`SOC Logs`, `Policy Docs`, `Email Headers`).
   - Verifica la preview delle entità abilitate prima della scansione.
3. **Avvia Scansione**: Il backend analizza i file e rileva le entità sensibili.
4. **Review**: Rivedi i "finding" proposti. Puoi deselezionare quelli che non vuoi pseudonimizzare.
5. **Applica**: Applica le modifiche. I file originali non vengono mai toccati.
6. **Risultati**: Nella sezione Results accedi a:
   - **Testo pseudonimizzato** — Copia negli appunti o scarica come .txt
   - **Passphrase visibile** — Mostri/nascondi e copia per l'uso successivo
   - **File mapping.enc** — Scarica il mapping cifrato (essenziale per reversi)
   - **ZIP finale** (per file) — Contiene documenti pseudonimizzati + report.html + report.json + mapping.enc

---

## 🤖 Integrazione con AI

Vuoi inviare i tuoi dati a un modello AI (ChatGPT, Claude, LLaMA) senza esporre informazioni sensibili?

### Workflow

1. **Pseudonimizza i tuoi dati** nel Tool (vedi sezione Utilizzo sopra)
2. **Nella sezione Results:**
   - Copia o scarica il **testo pseudonimizzato**
   - Scarica il file **mapping.enc** (cifrato, essenziale)
   - Copia e salva la **passphrase** (in luogo sicuro)
3. **Invia il testo pseudonimo all'AI** (non inviare mapping.enc o passphrase)
4. **Ricevi la risposta dall'AI** (contiene i tuoi pseudonimi)
5. **Usa il Revert Panel → "Decifra Risposta AI"** per reintegrare i dati originali

### Operazioni Disponibili

**Nel Revert Panel (tab separate):**
- **Decifra Risposta AI** — Decifra il testo pseudonimizzato ricevuto dall'AI usando mapping.enc + passphrase
- **Revert Batch ZIP** — Reversi completamente i file di un batch precedente

### Documentazione Completa

→ Vedi [docs/11_AI_Integration_and_Revert_Flows.md](docs/11_AI_Integration_and_Revert_Flows.md) per:
- Passaggio-per-passaggio del workflow Pseudonimizza → AI → Decifra
- Come scegliere una passphrase robusta
- Operazioni Revert e scenari di utilizzo
- Troubleshooting avanzato

---

## 📚 Documentation Guide

### Per Iniziare
- **[README.md](README.md)** — Questa pagina. Quick start e feature overview.
- **[docs/01_PRD.md](docs/01_PRD.md)** — Product requirements, caso d'uso e stack tecnico.

### Capire l'Architettura
- **[docs/02_Technical_Architecture.md](docs/02_Technical_Architecture.md)** — Architettura backend, flussi, dipendenze moduli.
- **[docs/03_Data_Model.md](docs/03_Data_Model.md)** — Schemi Pydantic e flusso dei dati.
- **[docs/06_Detector_Strategy.md](docs/06_Detector_Strategy.md)** — Strategia di detection (regex, dict, NER, pattern custom).

### Workflow & Usabilità
- **[docs/05_UX_Flow.md](docs/05_UX_Flow.md)** — Flussi utente interfaccia e casi d'uso.
- **[docs/04_Policies.md](docs/04_Policies.md)** — Policy preset (SOC Logs, Policy Docs, Email Headers).
- **[docs/11_AI_Integration_and_Revert_Flows.md](docs/11_AI_Integration_and_Revert_Flows.md)** — Integrazione AI, reversibilità, gestione passphrase.

### Testing & Qualità
- **[docs/07_Test_Plan_and_Metrics.md](docs/07_Test_Plan_and_Metrics.md)** — Strategia testing, metriche coverage.
- **[docs/15_CI_Quality_Gates.md](docs/15_CI_Quality_Gates.md)** — Automated quality gates (coverage thresholds, exception patterns).
- **[docs/14_Parser_Capability_Matrix.md](docs/14_Parser_Capability_Matrix.md)** — Feature matrix per parser, limitazioni note.

### Operational & Deployment
- **[docs/08_Risks_and_Mitigations.md](docs/08_Risks_and_Mitigations.md)** — Analisi rischi e mitigazioni.
- **[docs/17_Deployment_Profiles.md](docs/17_Deployment_Profiles.md)** — Profili deployment (DEV, STAGING, PROD), configurazione per ambiente.
- **[docs/16_Rate_Limit_Robustness.md](docs/16_Rate_Limit_Robustness.md)** — Rate limiting, cleanup auto, memory bounds.

### Planning & Roadmap
- **[docs/09_Roadmap.md](docs/09_Roadmap.md)** — Roadmap prodotto.
- **[docs/10_Backlog.md](docs/10_Backlog.md)** — Backlog item e priorità.
- **[docs/RELEASES.md](docs/RELEASES.md)** — Changelog, release notes e versioni.

---

## 🔐 Sicurezza e Limitazioni

- **Passphrase**: La sicurezza del mapping dipende dalla robustezza della passphrase. Usane una lunga e complessa (min 12 char, con maiuscole/minuscole/numeri/simboli).
- **Cookie di sessione**: Il backend imposta il cookie auth con flag `Secure` abilitato di default. Solo in sviluppo locale HTTP puoi disabilitarlo esplicitamente con `AUTH_SESSION_COOKIE_SECURE=false`.
- **OCR**: La qualità dell'OCR dipende dalla risoluzione e dalla chiarezza dell'immagine. Testo sfocato o scritto a mano potrebbe non essere rilevato.
- **Formule XLSX**: Le formule vengono ignorate e non pseudonimizzate per evitare di corrompere i fogli di calcolo.
- **Log di Installazione**: In caso di problemi durante l'installazione delle dipendenze, il log completo viene salvato in `install.log`.
- **Mapping.enc**: Una volta persa la passphrase, il file mapping.enc non è più recuperabile. Conservarlo in un luogo sicuro.
---

## 🛠️ Sviluppo

### Setup Ambiente Sviluppo

```bash
# Crea virtual environment
python3 -m venv .venv  # Python 3.11+ richiesto (3.12 usato in produzione)
source .venv/bin/activate  # Linux/macOS
# oppure .venv\Scripts\activate  # Windows

# Installa dipendenze backend
pip install -r backend/requirements.txt
```

### Frontend React (v5.0+)

Il frontend è stato modernizzato con **React 18**, **Tailwind CSS** e **dark mode**.

#### Setup Frontend

```bash
cd frontend
npm install
```

#### Dev (Vite + HMR)

```bash
# Terminal 1: Backend
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Frontend (Vite dev server)
cd frontend
npm run dev
```

Accedi a: `http://localhost:5173` (con API proxy a backend)

#### Build per Production

```bash
cd frontend
npm run build
```

Crea `frontend/dist/` che FastAPI servira' automaticamente in produzione.

#### Dev Mode (Full Stack)

```bash
make dev
```

Avvia sia backend che frontend in parallelo con HMR (Hot Module Reload). Backend su `:8000`, Frontend su `:5173` con hot reload.

Alternativamente, manuale:
```bash
./scripts/dev-stack.sh  # se preferisci lo script diretto
```

#### Caratteristiche Frontend

✨ **UI/UX**
- Dark mode toggle (persiste in localStorage)
- Responsive design mobile-first
- Smooth animations e transitions
- Toast notifications (success, error, warning, info)
- Drag-and-drop file upload

📊 **Workflow**
- Scanner unificato (testo + file)
- Policy preview real-time
- Findings table con review interattivo
- Custom pseudonym personalizzato
- Download ZIP con report (HTML + JSON)

🔧 **Tech Stack**
- React 18 con Hooks
- Tailwind CSS v3 (dark mode)
- Vite bundler (velocissimo)
- Axios for API calls
- Context API per state management



```bash
cd backend
pytest tests/ -v
pytest tests/test_api_contract.py -v
```

### Endpoint Operativi

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ready
curl http://127.0.0.1:8000/api/settings/policies
curl http://127.0.0.1:8000/api/settings/policies/SOC%20Logs
```

### Testing

**Test Suite Status:**
- ✅ **348 test passanti, 12 skippati** (Tesseract OCR non disponibile in CI)
  - `test_functional.py`: 49 test (detectors, parsers, sicurezza, crypto)
  - `test_auth_complete.py`: suite completa autenticazione e JWT
  - `test_csrf_middleware.py`: protezione CSRF globale
  - `test_api_contract.py`: contratti API (202 Accepted pattern)
  - `test_parser_limitations.py`: edge case parser
- 📊 **Coverage: 71%** — Moduli critici:
  - `crypto.py`: 95% (eccellente)
  - `schemas.py`: 98% (eccellente)
  - `safety.py`: 92% (eccellente)
  - `auth.py`: 79% (buono)
  - `pipeline.py`: 71% (buono)

**Test Infrastructure:**
- Celery EAGER mode per esecuzione sincrona in test (no broker necessario)
- Redis mocking con fallback in-memory
- Test di integrazione multicontainer separati (`pytest -m integration`, richiede Docker)

```bash
# Esegui tutti i test unitari (no Docker necessario)
cd backend
pytest tests/ -m "not integration" -v

# Con coverage report
pytest tests/ -m "not integration" --cov=app --cov-report=html

# Test di integrazione (richiede Docker Compose attivo)
pytest tests/ -m integration -v

# Tramite Makefile
make test       # test unitari
make test-cov   # con coverage report
```

### Struttura Progetto

```
pseudonymization-tool/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/               # API routes (/api/*)
│   │   ├── core/              # Business logic
│   │   ├── detectors/         # Entity detection (regex, dict, SOC)
│   │   ├── parsers/           # Document parsers (PDF, DOCX, XLSX, IMG)
│   │   ├── pseudonymizer/     # Transformation engine
│   │   ├── mapping/           # Crypto (AES-256 encryption)
│   │   ├── report/            # Report generation
│   │   └── models/            # Pydantic schemas
│   ├── config/                # Configuration files
│   ├── tests/                 # Unit & integration tests
│   └── requirements.txt
├── frontend/                  # React 18 + Tailwind CSS
│   ├── src/
│   │   ├── components/        # React components
│   │   │   ├── Header.jsx
│   │   │   ├── Scanner.jsx
│   │   │   ├── FindingsTable.jsx
│   │   │   └── Results.jsx
│   │   ├── context/           # Context API (dark mode)
│   │   ├── hooks/             # Custom hooks (useToast)
│   │   ├── App.jsx            # Root component
│   │   ├── main.jsx           # Entry point
│   │   └── index.css          # Tailwind imports
│   ├── dist/                  # Build output (production)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
├── scripts/
│   ├── dev-stack.sh           # Development mode helper
│   ├── verify_features.py     # Feature verification script
│   └── legacy/                # Venv-based startup scripts (air-gapped)
│       ├── start.sh           # Linux/macOS startup
│       ├── start.bat          # Windows startup
│       ├── prepare_offline.sh # Offline preparation
│       ├── prepare_offline.bat
│       └── README.md          # Legacy installation guide
├── docs/                      # Documentation & Roadmap
├── Makefile                   # Universal command interface
├── docker-compose.yml         # Docker orchestration
└── README.md
```

---

## 🤝 Contributing

Le contribuzioni sono benvenute! Per contribuire:

1. Fork del progetto
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Commit delle modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Push al branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

Leggi la [documentazione tecnica](docs/02_Technical_Architecture.md) per comprendere l'architettura.

---

## 📄 Licenza

Questo progetto è distribuito sotto licenza MIT. Vedi il file `LICENSE` per maggiori dettagli.

---

## 🙏 Riconoscimenti

- **Tesseract OCR** per il riconoscimento ottico dei caratteri
- **FastAPI** per il framework web
- **python-docx, openpyxl, pypdf** per il parsing dei documenti
- Community open source per i contributi e il feedback
