# Backlog di Progetto (MVP)

**Autore:** Manus AI
**Versione:** 1.0 (MVP)
**Data:** 2026-02-25

---

## 1. Introduzione

Questo documento rappresenta il backlog di lavoro per lo sviluppo dell'MVP del Local Pseudonymization Tool. I task sono organizzati in epic, prioritizzati e includono criteri di accettazione chiari per guidare l'implementazione e i test.

## 2. Epic e User Story

### Epic 1: Setup del Progetto e Pipeline di Base

*Come sviluppatore, voglio un'infrastruttura di progetto solida e una pipeline di elaborazione funzionante per poter costruire le funzionalità principali in modo efficiente.*

| ID | Task | Priorità | Criteri di Accettazione |
|---|---|---|---|
| **B-01** | Inizializzare la struttura del progetto (backend/frontend) | **Massima** | - Creata la directory di progetto `pseudonymization-tool`. - Setup del backend FastAPI con una cartella `app/`. - Creata la cartella `frontend/` con `index.html`, `style.css`, `script.js`. - Inizializzato un ambiente virtuale Python. |
| **B-02** | Implementare il modello dati con Pydantic | **Massima** | - I modelli `Batch`, `Finding`, `ReviewDecision`, etc., sono definiti in Pydantic. - I modelli sono validati e serializzabili in JSON. |
| **B-03** | Creare il gestore di batch e la pipeline di orchestrazione | **Massima** | - Il backend può creare un nuovo batch e assegnargli un ID univoco. - Esiste una funzione che orchestra la chiamata sequenziale dei moduli (Parse, Detect, etc.). - Lo stato del batch viene tracciato correttamente. |
| **B-04** | Implementare il modulo di cifratura/decifratura del mapping | **Alta** | - Una funzione può cifrare un dizionario Python in un file binario usando una passphrase. - Una funzione può decifrare il file usando la stessa passphrase. - La decifratura fallisce con una passphrase errata. |

### Epic 2: Supporto ai Formati di File

*Come utente, voglio poter caricare diversi tipi di file e avere la certezza che il loro contenuto testuale venga estratto correttamente per l'analisi.*

| ID | Task | Priorità | Criteri di Accettazione |
|---|---|---|---|
| **F-01** | Implementare il parser per file di testo (`.txt`, `.md`, `.csv`) | **Massima** | - Il contenuto di questi file viene letto come stringa di testo. - La codifica (UTF-8) è gestita correttamente. |
| **F-02** | Implementare il parser per `.docx` | **Massima** | - Il testo dal corpo principale, header e footer del documento viene estratto. - La libreria `python-docx` è integrata. |
| **F-03** | Implementare il parser per `.xlsx` | **Massima** | - Il testo viene estratto solo dalle celle contenenti stringhe. - Le celle contenenti formule vengono ignorate e segnalate. - La libreria `openpyxl` è integrata. |
| **F-04** | Implementare il parser per `.pdf` testuali | **Alta** | - Il testo viene estratto da PDF nativamente testuali. - I PDF basati su immagini o cifrati vengono identificati e segnalati con un warning. - La libreria `pypdf` è integrata. |
| **F-05** | Implementare il parser per immagini (`.jpg`, `.png`) | **Massima** | - Il motore OCR Tesseract è integrato e configurato per le lingue `ita` e `eng`. - Il testo e i bounding box vengono estratti dall'immagine. - La libreria `Pillow` è usata per la manipolazione delle immagini. - I metadati EXIF vengono rimossi. |

### Epic 3: Motore di Rilevamento (Detector)

*Come utente, voglio che il sistema identifichi in modo affidabile un'ampia gamma di dati sensibili presenti nei miei file.*

| ID | Task | Priorità | Criteri di Accettazione |
|---|---|---|---|
| **D-01** | Implementare i detector basati su regex | **Massima** | - Sono stati creati detector regex per Email, IPv4, URL, Codice Fiscale, P.IVA e Numeri di Telefono. - Ogni detector restituisce un `Finding` con la confidenza appropriata. |
| **D-02** | Implementare il detector basato su dizionario | **Alta** | - Il sistema può caricare termini da file `.txt` in una directory di configurazione. - Il detector trova corrispondenze case-insensitive nel testo. |
| **D-03** | Gestire le sovrapposizioni dei detector | **Media** | - È implementata una logica per risolvere i conflitti quando più detector trovano corrispondenze sovrapposte (es. priorità al match più lungo). |

### Epic 4: Workflow Utente (UI/UX)

*Come utente, voglio un'interfaccia chiara e semplice per caricare file, revisionare i risultati e ottenere i miei file pseudonimizzati.*

| ID | Task | Priorità | Criteri di Accettazione |
|---|---|---|---|
| **U-01** | Sviluppare la pagina di upload e configurazione | **Massima** | - L'utente può trascinare o selezionare file. - L'utente può scegliere la modalità e inserire una passphrase. - Il pulsante di avvio si attiva solo quando la configurazione è completa. |
| **U-02** | Sviluppare la schermata di review manuale | **Massima** | - I `Finding` vengono visualizzati in una tabella filtrabile. - L'utente può cambiare la decisione (`Accetta`, `Escludi`, `Modifica`) per ogni riga. - Le decisioni vengono inviate correttamente al backend. |
| **U-3** | Sviluppare la redazione visuale per le immagini | **Alta** | - Nella review, le immagini mostrano i box di redazione proposti. - L'immagine finale generata ha i box di redazione applicati. |
| **U-04** | Sviluppare la pagina di download finale | **Massima** | - Al termine del processo, vengono presentati i link per scaricare un archivio ZIP con gli output, i report e il mapping. |
| **U-05** | Implementare la modalità Dry-Run | **Media** | - Se il flag `is_dry_run` è attivo, la pipeline si ferma dopo la fase di detection e review, senza applicare modifiche. |

### Epic 5: Sicurezza e Packaging

*Come utente, voglio avere la certezza che il tool sia sicuro e facile da installare sul mio PC Windows.*

| ID | Task | Priorità | Criteri di Accettazione |
|---|---|---|---|
| **S-01** | Garantire il binding del server su `127.0.0.1` | **Massima** | - Il server Uvicorn è configurato per ascoltare solo sull'interfaccia di loopback. |
| **S-02** | Implementare la pulizia dei file temporanei | **Massima** | - La directory del batch viene eliminata al termine del processo, sia in caso di successo che di errore. |
| **S-03** | Sanitizzare i log | **Alta** | - Nessun valore di dato sensibile originale viene scritto nei log dell'applicazione. |
| **S-04** | Creare interfaccia di avvio unificata | **Alta** | - Makefile con comandi standard (`make start`, `make dev`, `make test`) come interfaccia primaria. - Docker Compose per deployment containerizzato. - Script legacy in `scripts/legacy/` per ambienti air-gapped senza Docker. |
| **S-05** | Scrivere la documentazione utente (README) | **Alta** | - Il file `README.md` contiene istruzioni chiare per l'installazione, l'uso, la configurazione dei dizionari e le limitazioni note. |
