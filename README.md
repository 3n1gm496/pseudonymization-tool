# Local Pseudonymization Tool

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Web application locale per la pseudonimizzazione sicura di dati sensibili in documenti di testo, DOCX, XLSX, PDF e immagini. Progettato per ambienti enterprise che richiedono massima sicurezza e capacità di operare completamente offline.

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

- [Prerequisiti](#-prerequisiti)
- [Installazione](#-installazione-e-avvio)
- [Utilizzo](#-utilizzo)
- [Sicurezza](#-sicurezza-e-limitazioni)
- [Sviluppo](#-sviluppo)
- [Contributing](#-contributing)
- [Licenza](#-licenza)

---

## 🔧 Prerequisiti

### 1.1. Python (Obbligatorio)

| Versione | Supporto | Note |
|---|---|---|
| **3.11.x** | ✅ **Raccomandata e Testata** | La versione usata per lo sviluppo e i test. |
| 3.10.x | ⚠️ Supportata (fallback) | Dovrebbe funzionare, ma non è la versione primaria di test. |
| 3.12.x | ⚠️ Supportata (fallback) | Idem. |
| < 3.10 | ❌ **Non supportata** | Lo script di avvio si fermerà. |
| >= 3.13 | ❌ **Non supportata** | Lo script di avvio si fermerà per evitare problemi di compatibilità non noti. |

**Installazione (Windows):**
1. Scarica **Python 3.11.9** da [python.org](https://www.python.org/downloads/release/python-3119/).
2. Durante l'installazione, **seleziona l'opzione "Add Python to PATH"**.

### 1.2. Tesseract OCR (Opzionale)

Questo componente è necessario **solo per processare testo contenuto in immagini** (JPG, PNG).

**Installazione (Windows):**
1. Scarica l'installer da [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
2. Durante l'installazione, assicurati di selezionare i language pack aggiuntivi, in particolare **Italiano**.

### 1.3. Prerequisiti di Build (Windows)

**Nessuno.** Le dipendenze Python usate sono distribuite come *wheel* pre-compilati per Windows. **Non sono richiesti Visual C++ Build Tools** o altri compilatori C/Rust.

---

## 🚀 Installazione e Avvio

### 2.1. Modalità Online (connessione internet richiesta solo la prima volta)

1. **Decomprimi** il file `pseudonymization-tool-v1.0.3.zip`.
2. Esegui lo script di avvio:
   - **Windows**: Doppio clic su `start.bat`.
   - **Linux/macOS**: Apri un terminale e digita `chmod +x start.sh && ./start.sh`.
3. La prima volta, lo script creerà un ambiente virtuale (`.venv/`) e installerà le dipendenze. Questo richiede qualche minuto e una connessione internet.
4. Il browser si aprirà automaticamente su `http://localhost:8000`.

Le esecuzioni successive saranno istantanee e completamente offline.

### 2.2. Modalità Offline (per macchine senza accesso a internet)

Questa modalità permette di preparare il pacchetto su una macchina con internet e poi eseguirlo su una macchina target completamente isolata.

**Passo 1: Sulla macchina CON internet**

1. Decomprimi il file ZIP.
2. Esegui lo script `prepare_offline`:
   - **Windows**: Doppio clic su `prepare_offline.bat`.
   - **Linux/macOS**: Apri un terminale e digita `chmod +x prepare_offline.sh && ./prepare_offline.sh`.
3. Lo script creerà una cartella `wheelhouse/` con tutti i file delle dipendenze (`.whl`).

**Passo 2: Sulla macchina TARGET (senza internet)**

1. Copia l'**intera cartella** del tool (inclusa la sottocartella `wheelhouse/`) sulla macchina target.
2. Esegui lo script `start.bat` o `start.sh` come al solito.
3. Lo script rileverà automaticamente la presenza di `wheelhouse/` e installerà le dipendenze da lì, **senza richiedere alcuna connessione internet**.

### 2.3. Modalità Docker Compose

Questa modalità fornisce un avvio standardizzato dell'app in container, in linea con approcci infrastrutturali tipo `security-scanning-platform`.

```bash
cd pseudonymization-tool
docker compose up --build -d
```

Verifica servizio:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ready
```

Stop:

```bash
docker compose down
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

## 🔐 Sicurezza e Limitazioni

- **Passphrase**: La sicurezza del mapping dipende dalla robustezza della passphrase. Usane una lunga e complessa.
- **OCR**: La qualità dell'OCR dipende dalla risoluzione e dalla chiarezza dell'immagine. Testo sfocato o scritto a mano potrebbe non essere rilevato.
- **Formule XLSX**: Le formule vengono ignorate e non pseudonimizzate per evitare di corrompere i fogli di calcolo.
- **Log di Installazione**: In caso di problemi durante l'installazione delle dipendenze, il log completo viene salvato in `install.log`.
---

## 🛠️ Sviluppo

### Setup Ambiente Sviluppo

```bash
# Crea virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# oppure .venv\Scripts\activate  # Windows

# Installa dipendenze
pip install -r backend/requirements.txt

# Avvia backend in modalità dev
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Esecuzione Test

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

### Esecuzione via Docker

```bash
docker compose up --build
```

Note operative container:
- Le configurazioni dizionario sono montate da `backend/config`.
- I dati temporanei batch sono su volume Docker dedicato `pseudonymizer_tmp`.
- OCR (`tesseract`) è incluso nell'immagine.

### Struttura Progetto

```
pseudonymization-tool/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── api/         # API routes
│   │   ├── core/        # Business logic
│   │   ├── detectors/   # Entity detection
│   │   ├── parsers/     # Document parsers
│   │   ├── pseudonymizer/  # Transformation engine
│   │   └── report/      # Report generation
│   └── config/          # Configuration files
├── frontend/            # Static HTML/CSS/JS
└── docs/               # Documentation
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