_# Architettura Tecnica — Local Pseudonymization Tool

**Autore:** Manus AI
**Versione:** 1.0 (MVP)
**Data:** 2026-02-25

---

## 1. Panoramica dell'Architettura

L'applicazione è progettata come una **single-page web application (SPA)** servita da un backend Python locale. L'architettura è completamente offline e contenuta, senza dipendenze da servizi esterni. Il server backend espone API RESTful consumate dal frontend e orchestra la pipeline di elaborazione dei file.

Il sistema è suddiviso in tre macro-componenti:

1.  **Frontend:** Un'interfaccia web statica (HTML, JS, CSS) responsabile dell'interazione con l'utente.
2.  **Backend:** Un server API (FastAPI) che gestisce le richieste, lo stato del batch e la pipeline di elaborazione.
3.  **Processing Pipeline:** Una serie di moduli Python disaccoppiati che eseguono le operazioni di parsing, detection, pseudonimizzazione e reporting.

![Diagramma Architettura](https://i.imgur.com/example.png)  <-- *Placeholder per un diagramma che verrà generato in seguito*

## 2. Componenti Dettagliati

### 2.1. Frontend

- **Stack:** HTML5, CSS3, JavaScript (Vanilla). Nessun framework (es. React, Vue) per l'MVP per garantire semplicità, assenza di build-step complessi e zero dipendenze esterne (CDN).
- **Comunicazione:** Interagisce con il backend esclusivamente tramite chiamate `fetch` alle API RESTful esposte su `127.0.0.1:8000`.
- **Responsabilità:**
    - Gestire l'upload dei file (drag & drop).
    - Raccogliere i parametri di configurazione del batch (modalità Light/Strict, passphrase).
    - Invocare l'avvio della scansione.
    - Mostrare i risultati della scansione nella schermata di review.
    - Inviare le decisioni della review manuale al backend.
    - Gestire il download dei file finali (artefatti pseudonimizzati, report, mappa cifrata).

### 2.2. Backend (Server API)

- **Stack:** Python 3.11+ con **FastAPI** e **Uvicorn** come server ASGI.
- **Binding:** Il server sarà configurato per ascoltare esclusivamente sull'indirizzo di loopback `127.0.0.1` per impedire accessi dalla rete locale.
- **API Endpoints (principali):**
    - `POST /api/batches`: Crea un nuovo batch, carica i file in una directory temporanea.
    - `POST /api/batches/{batch_id}/scan`: Avvia la pipeline di scansione per un dato batch.
    - `GET /api/batches/{batch_id}/findings`: Recupera la lista delle entità trovate per la review manuale.
    - `POST /api/batches/{batch_id}/review`: Invia le decisioni della review (accetta, modifica, escludi).
    - `POST /api/batches/{batch_id}/apply`: Applica le trasformazioni finali.
    - `GET /api/batches/{batch_id}/download`: Prepara e restituisce un archivio ZIP con gli output.
- **Gestione dello Stato:** Lo stato di ogni batch (file, configurazione, risultati) è gestito su filesystem in una directory temporanea dedicata (es. `/tmp/pseudonymizer/<batch_id>`).

### 2.3. Processing Pipeline

La pipeline è un insieme di moduli Python orchestrati dal backend. Per ogni file in un batch, vengono eseguiti i seguenti passaggi in sequenza:

1.  **Parser Module:**
    - **Input:** Un file (es. `document.docx`).
    - **Logica:** Seleziona il parser appropriato in base all'estensione del file (`.txt`, `.docx`, `.pdf`, `.xlsx`, `.png`, etc.).
    - **Output:** Un oggetto intermedio contenente il testo estratto e i metadati rilevanti (es. per le immagini, il testo OCR e i bounding box).
    - **Tecnologie:** `pypdf` per PDF, `python-docx` per DOCX, `openpyxl` per XLSX, `Pillow` e un wrapper per **Tesseract OCR** per le immagini.

2.  **Detector Module:**
    - **Input:** L'oggetto testo estratto dal parser.
    - **Logica:** Applica una serie di detector in sequenza:
        - **Regex-based detectors:** Per entità con pattern definiti (IP, email, CF, P.IVA, URL).
        - **Dictionary-based detectors:** Per termini specifici dell'organizzazione (da file di configurazione custom).
    - **Output:** Una lista di `Finding`, ognuno contenente il valore originale, il tipo di entità, la posizione nel testo e un punteggio di confidenza.

3.  **Pseudonymizer Module:**
    - **Input:** La lista di `Finding` originali.
    - **Logica:** Per ogni `Finding`, genera uno pseudonimo basato sulla modalità (Light/Strict) e sul tipo di entità. Mantiene la consistenza all'interno del batch utilizzando una mappa in memoria.
    - **Output:** Una mappa che associa ogni valore originale al suo pseudonimo proposto (es. `{"mario.rossi@ente.gov.it": "user_001@orgdom_001.gov.it"}`).

4.  **Review & Transform Module:**
    - **Input:** La lista di `Finding` con gli pseudonimi proposti e le decisioni dell'utente dalla review manuale.
    - **Logica:** Crea la versione finale dei file sostituendo i valori originali con gli pseudonimi approvati dall'utente.
    - **Output:** I file pseudonimizzati.

5.  **Mapping & Report Module:**
    - **Input:** La mappa finale delle sostituzioni e i metadati del processo.
    - **Logica:**
        - Genera il file di mapping (valore originale -> pseudonimo).
        - Cifra il file di mapping usando la passphrase del batch (`cryptography`).
        - Genera il report finale in formato JSON e HTML.
    - **Output:** `mapping.enc`, `report.json`, `report.html`.

## 3. Sicurezza e Isolamento

- **Nessuna Chiamata di Rete:** Verranno implementati controlli (possibilmente tramite monkey-patching delle librerie standard come `socket` o `requests` in una modalità di test/verifica) per assicurare che nessuna dipendenza di terze parti tenti di comunicare con l'esterno.
- **Gestione File Temporanei:** Tutti i file intermedi e caricati risiedono in una directory temporanea (`/tmp/pseudonymizer`) che viene creata all'avvio del batch e distrutta al termine o in caso di errore, per non lasciare tracce sul disco.
- **Logging Sanitizzato:** I log di produzione non conterranno mai i valori originali dei dati sensibili, ma solo metadati (es. "Trovate 3 entità di tipo EMAIL nel file X").

## 4. Packaging e Deployment (MVP)

Il rilascio consiste in:

**Metodo Raccomandato: Docker**
- Dockerfile multi-stage (frontend React + backend FastAPI)
- docker-compose.yml per orchestrazione
- Makefile con comandi unificati (`make start`, `make dev`, `make test`)
- README.md con quick start Docker-first

**Metodo Alternativo: Installazione Locale (Air-gapped)**
- Script in `scripts/legacy/` per ambienti senza Docker:
  - `start.sh` / `start.bat`: Crea venv, installa dipendenze, avvia server
  - `prepare_offline.sh` / `.bat`: Prepara wheelhouse per installazione offline
- Documentazione dedicata in `scripts/legacy/README.md`
- Cartella `config/` con dizionari custom
