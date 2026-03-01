# Local Pseudonymization Tool v4.0

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 18](https://img.shields.io/badge/React-18.2-61dafb.svg)](https://react.dev)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.3-38b2ac.svg)](https://tailwindcss.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)

Web application locale moderna per la pseudonimizzazione sicura di dati sensibili in documenti di testo, DOCX, XLSX, PDF e immagini. Interfaccia React con Tailwind CSS, darkmode supportato. Progettato per ambienti enterprise che richiedono massima sicurezza e capacità di operare completamente offline.

🔗 **Repository:** [github.com/3n1gm496/pseudonymization-tool](https://github.com/3n1gm496/pseudonymization-tool)

## ✨ Caratteristiche

- **🔒 100% Offline** — Nessuna chiamata di rete esterna, tutti i dati rimangono sulla macchina locale
- **📄 Multi-formato** — Supporto per TXT, CSV, MD, DOCX, XLSX, PDF (testuali), JPG, PNG
- **🔐 Sicurezza Avanzata** — Mapping cifrato con passphrase AES-256, zero logging di dati sensibili
- **⚙️ Modalità Flessibili** — `light` (solo entità di rete) e `strict` (tutte le entità PII)
- **🧭 Input Unificato** — testo inline e upload documenti disponibili nello stesso flusso
- **🛡️ Preset Policy** — `SOC Logs`, `Policy Docs`, `Email Headers` con preview entità abilitate
- **👁️ Review Manuale** — Interfaccia per rivedere e approvare/rifiutare ogni pseudonimo proposto
- **📊 Report Dettagliati** — HTML navigabile e JSON strutturato per audit trail
- **✅ Readiness API** — endpoint `/api/ready` per distinguere processo attivo da servizio pronto
- **🎯 Deterministico** — Stesso input = stesso output con la stessa passphrase

---

## 📋 Indice

- [Quick Start](#-quick-start)
- [Utilizzo](#-utilizzo)
- [Integrazione AI](#-integrazione-con-ai---prepara-per-ai)
- [Sicurezza](#-sicurezza-e-limitazioni)
- [Sviluppo](#-sviluppo)
- [Contributing](#-contributing)
- [Licenza](#-licenza)

---

## ⚡ Quick Start

### Metodo 1: Docker (Raccomandato)

**Prerequisiti**: Docker e Docker Compose installati

```bash
# Clone del repository
git clone https://github.com/3n1gm496/pseudonymization-tool.git
cd pseudonymization-tool

# Avvio con Docker
make start
```

Oppure manualmente:

```bash
docker compose up --build -d
```

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
- Installazione con Python venv
- Modalità offline (machine senza internet)
- Preparazione pacchetto wheelhouse
- Troubleshooting prerequisiti (Python, Tesseract)

**Quick command:**
```bash
make legacy-start
```

---

## 💡 Utilizzo

1. **Upload**: Trascina i file da processare nell'area di upload.
2. **Configura**: Seleziona la modalità (`light` o `strict`) e inserisci una **passphrase robusta** (essenziale per la sicurezza del mapping).
   - Seleziona il preset policy (`SOC Logs`, `Policy Docs`, `Email Headers`).
   - Verifica la preview delle entità abilitate prima della scansione.
3. **Avvia Scansione**: Il backend analizza i file e rileva le entità sensibili.
4. **Review**: Rivedi i "finding" proposti. Puoi deselezionare quelli che non vuoi pseudonimizzare.
5. **Applica**: Applica le modifiche. I file originali non vengono mai toccati.
6. **Download**: Scarica un file ZIP contenente:
   - `files/`: i documenti pseudonimizzati.
   - `report.html`: un report navigabile dei finding e delle sostituzioni.
   - `report.json`: i dati grezzi del report.
   - `mapping.enc`: il file di mapping **cifrato** con la tua passphrase. **Conservalo** per garantire la consistenza tra diversi batch.

---

## 🤖 Integrazione con AI - "Prepara per AI"

Vuoi inviare i tuoi dati a un modello AI (ChatGPT, Claude, LLaMA) senza esporre informazioni sensibili?

### Workflow

1. **Pseudonimizza i tuoi dati** nel Tool (vedi sezione Utilizzo sopra)
2. **Scarica il testo pseudonimizzato** dalla sezione risultati
3. **Scarica il file `mapping.enc` cifrato** (nel drawer "Prepara per AI")
4. **Invia il testo pseudonimo all'AI** (non inviare il mapping.enc o la passphrase)
5. **Ricevi la risposta dall'AI** (che contiene i tuoi pseudonimi)
6. **Usa il tab "Decifera Risposta AI"** per reintegrare i dati originali

### Sicurezza

- ✅ Dati originali **MAI inviati** a terze parti
- ✅ Mapping cifrato con **AES-256-GCM + PBKDF2-600k**
- ✅ Passphrase **NON inviata** con il mapping
- ✅ Nulla può essere decifrato senza la passphrase

### Documentazione Completa

→ Vedi [docs/11_AI_Integration_and_Revert_Flows.md](docs/11_AI_Integration_and_Revert_Flows.md) per:
- Passaggio-per-passaggio dei tre flussi (Prepara per AI, Decifera Risposta, Revert Batch ZIP)
- Come scegliere una passphrase robusta
- Exemple workflow completo
- Troubleshooting

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
python3.11 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# oppure .venv\Scripts\activate  # Windows

# Installa dipendenze backend
pip install -r backend/requirements.txt
```

### Frontend React (v4.0+)

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

```bash
# Esegui tutti i test
make test

# Con coverage report
make test-cov

# Test specifici
cd backend
pytest tests/test_api_contract.py -v
```

### Struttura Progetto

```
pseudonymization-tool/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/               # API routes (/api/*)
│   │   ├── core/              # Business logic
│   │   ├── detectors/         # Entity detection (regex, dict, ML, SOC)
│   │   ├── parsers/           # Document parsers (PDF, DOCX, XLSX, IMG)
│   │   ├── pseudonymizer/     # Transformation engine
│   │   ├── mapping/           # Crypto (AES-256 encryption)
│   │   ├── report/            # Report generation
│   │   └── models/            # Pydantic schemas
│   ├── config/                # Configuration files
│   ├── tests/                 # Unit & integration tests (60+)
│   └── requirements.txt
├── frontend/                  # React 18 + Tailwind CSS (v4.0+)
│   ├── src/
│   │   ├── components/        # React components
│   │   │   ├── Header.jsx
│   │   │   ├── Scanner.jsx
│   │   │   ├── PolicySelector.jsx
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
- **python-docx, openpyxl, PyPDF2** per il parsing dei documenti
- Community open source per i contributi e il feedback