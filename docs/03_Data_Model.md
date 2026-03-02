# Modello Dati — Local Pseudonymization Tool

**Autore:** Manus AI
**Versione:** 4.1.0 (Phase 4)
**Data:** 2026-03-02

---

## 1. Introduzione

Questo documento definisce le principali strutture dati utilizzate all'interno dell'applicazione, sia per la logica di business interna sia per l'output finale. Il modello dati è progettato per essere semplice, serializzabile in JSON e per supportare il workflow di pseudonimizzazione, dalla rilevazione alla review e al reporting.

**Phase 4 Update:** Aggiunta supporto per elaborazione asincrona con Celery + Redis, inclusi nuovi campi per task tracking e strutture dati per caching distribuit o.

## 2. Strutture Dati Principali

### 2.1. `Batch`

Rappresenta una singola sessione di lavoro avviata dall'utente. Contiene tutti i file, la configurazione e i risultati associati.

| Campo | Tipo | Descrizione |
|---|---|---|
| `batch_id` | `string` (UUID) | Identificativo univoco per la sessione di lavoro. |
| `created_at` | `string` (ISO 8601) | Timestamp di creazione del batch. |
| `config` | `BatchConfig` | Oggetto contenente la configurazione scelta dall'utente. |
| `status` | `string` | Stato corrente del batch (es. `pending`, `scanning`, `review`, `done`, `error`). |
| `task_id` | `string` (UUID) | **[Phase 4]** Celery task ID per tracking asincrono. Null se task non ancora creato. |
| `files` | `list[FileRecord]` | Lista dei file caricati nel batch. |
| `findings` | `list[Finding]` | Lista aggregata di tutte le entità sensibili trovate in tutti i file del batch. |

**Phase 4 Status Flow:**
```
pending → started → scanning → review → done
                  ↓ (error case)
                error
```

### 2.2. `BatchConfig`

Contiene le impostazioni specifiche per un `Batch`.

| Campo | Tipo | Descrizione |
|---|---|---|
| `mode` | `string` | Modalità di pseudonimizzazione scelta: `light` o `strict`. |
| `passphrase_hash` | `string` (SHA256) | Hash della passphrase fornita dall'utente. L'hash viene usato solo per verifica interna, la passphrase grezza non viene mai memorizzata. |
| `is_dry_run` | `boolean` | Flag che indica se si tratta di una scansione in modalità "dry-run". |

### 2.3. `FileRecord`

Rappresenta un singolo file all'interno di un `Batch`.

| Campo | Tipo | Descrizione |
|---|---|---|
| `file_id` | `string` (UUID) | Identificativo univoco per il file all'interno del batch. |
| `original_name` | `string` | Nome del file originale caricato dall'utente. |
| `status` | `string` | Stato di processamento del file (es. `parsed`, `processed`, `failed`). |
| `error_message` | `string` | Eventuale messaggio di errore se il processamento fallisce. |

### 2.4. `Finding`

È la struttura dati centrale, che rappresenta una singola occorrenza di un'entità sensibile trovata in un file.

| Campo | Tipo | Descrizione |
|---|---|---|
| `finding_id` | `string` (UUID) | Identificativo univoco per il finding. |
| `file_id` | `string` | ID del file in cui è stato trovato il finding. |
| `entity_type` | `string` | Tipo di entità rilevata (es. `EMAIL`, `IPV4`, `PERSON`, `CODICE_FISCALE`). |
| `original_value` | `string` | Il valore originale del dato sensibile trovato. |
| `proposed_pseudonym` | `string` | Lo pseudonimo generato dal sistema. |
| `location` | `object` | Informazioni sulla posizione del finding nel file (es. numero di riga/colonna, bounding box per le immagini). |
| `confidence_score` | `float` | Punteggio di confidenza della rilevazione (da 0.0 a 1.0). |
| `detector_name` | `string` | Nome del detector che ha identificato l'entità (es. `RegexIpDetector`, `CustomDictionaryDetector`). |
| `review_decision` | `ReviewDecision` | La decisione presa dall'utente durante la fase di review. Inizialmente `null`. |

### 2.5. `ReviewDecision`

Modella la scelta dell'utente per un dato `Finding`.

| Campo | Tipo | Descrizione |
|---|---|---|
| `decision` | `string` | La decisione: `accept` (accetta lo pseudonimo), `reject` (ignora il finding), `modify` (usa uno pseudonimo custom). |
| `modified_pseudonym` | `string` | Lo pseudonimo personalizzato fornito dall'utente (usato solo se `decision` è `modify`). Può essere `null`. |

## 3. Strutture Dati per l'Output

### 3.1. `EncryptedMapping`

Il file di mapping (`mapping.enc`) è un file binario che contiene la versione serializzata e cifrata (AES-GCM) della mappa di reversibilità. La struttura dati prima della cifratura è un semplice dizionario JSON.

**Struttura JSON (prima della cifratura):**
```json
{
  "batch_id": "...",
  "created_at": "...",
  "mapping": {
    "user_001@orgdom_001.gov.it": "mario.rossi@ente.gov.it",
    "PERSON_001": "Mario Rossi",
    "IPV4_001": "10.24.8.15"
  }
}
```

### 3.2. `Report`

Il report finale, disponibile in JSON e HTML, fornisce un riepilogo completo del batch.

**Struttura JSON (`report.json`):**
```json
{
  "batch_id": "...",
  "started_at": "...",
  "completed_at": "...",
  "config": {
    "mode": "light",
    "is_dry_run": false
  },
  "summary": {
    "total_files_processed": 5,
    "files_with_findings": 3,
    "files_failed": 0,
    "total_findings": 42
  },
  "findings_by_type": {
    "EMAIL": 15,
    "IPV4": 20,
    "CODICE_FISCALE": 7
  },
  "processed_files": [
    {
      "original_name": "logs.txt",
      "status": "processed",
      "findings_count": 35
    },
    {
      "original_name": "document.pdf",
      "status": "processed_with_warnings",
      "warnings": ["Il PDF non era testuale, OCR non eseguito come da policy MVP."]
    }
  ],
  "warnings_and_limits": [
    "1 file PDF non è stato processato perché non conteneva testo estraibile."
  ]
}
```
L'HTML (`report.html`) sarà una versione ben formattata e leggibile di questi stessi dati.

---

## 4. Phase 4: Async Data Structures (Celery + Redis)

### 4.1. Redis Keys

**Task Queue:**
- `celery`: List, contiene task pendenti
- `celery-task-meta-{task_id}`: Hash, metadati e risultati del task

**Batch Progress Cache:**
- `batch:{batch_id}:progress`: String, percentuale di completamento (0-100)
- `batch:{batch_id}:status`: String, stato corrente (pending/started/success/failure)
- `batch:{batch_id}:error`: String, messaggio di errore (se applicabile)

**Task Results (TTL: 24h):**
- `celery-task-meta-{task_id}`: Hash con chiavi:
  - `status`: PENDING | STARTED | SUCCESS | FAILURE
  - `result`: JSON serialized result (se SUCCESS)
  - `traceback`: Stack trace (se FAILURE)
  - `date_done`: Timestamp completamento

### 4.2. Task Metadata Structure

**Celery Task Result (SUCCESS):**
```json
{
  "status": "SUCCESS",
  "result": {
    "batch_id": "abc-123-def-456",
    "findings_count": 42,
    "files_processed": 5,
    "duration_seconds": 127.45,
    "completed_at": "2026-03-02T14:35:22Z"
  },
  "traceback": null,
  "children": [],
  "date_done": "2026-03-02T14:35:22.123456"
}
```

**Celery Task Result (FAILURE):**
```json
{
  "status": "FAILURE",
  "result": {
    "exc_type": "FileNotFoundError",
    "exc_message": "File not found: uploads/batch_abc123/document.pdf"
  },
  "traceback": "Traceback (most recent call last):\n  File ...",
  "children": [],
  "date_done": "2026-03-02T14:35:22.123456"
}
```

**Progress Update (PROGRESS state):**
```json
{
  "status": "PROGRESS",
  "result": {
    "progress": 45,
    "current_file": "document3.pdf",
    "files_processed": 2,
    "total_files": 5,
    "message": "Processing document3.pdf..."
  }
}
```

### 4.3. API Response Structures (Phase 4)

**POST /api/batches (202 Accepted):**
```json
{
  "batch_id": "abc-123-def-456",
  "task_id": "xyz-789-uvw-012",
  "status": "pending",
  "message": "Scan enqueued, poll /api/batches/{id}/status for updates"
}
```

**GET /api/batches/{id}/status:**

*Pending:*
```json
{
  "batch_id": "abc-123-def-456",
  "status": "pending",
  "progress": 0,
  "message": "Task in queue, waiting for worker"
}
```

*Running:*
```json
{
  "batch_id": "abc-123-def-456",
  "status": "running",
  "progress": 45,
  "current_file": "document3.pdf",
  "files_processed": 2,
  "total_files": 5,
  "message": "Processing document3.pdf..."
}
```

*Completed:*
```json
{
  "batch_id": "abc-123-def-456",
  "status": "completed",
  "progress": 100,
  "result": {
    "findings_count": 42,
    "files_processed": 5,
    "duration_seconds": 127.45
  },
  "message": "Scan completed successfully"
}
```

*Failed:*
```json
{
  "batch_id": "abc-123-def-456",
  "status": "failed",
  "error": "FileNotFoundError: File not found: uploads/batch_abc123/document.pdf",
  "message": "Scan failed, see error for details"
}
```

### 4.4. Database Schema Updates (Phase 4)

**Batch Table (SQLite/PostgreSQL):**
```sql
CREATE TABLE batches (
    id TEXT PRIMARY KEY,           -- UUID batch_id
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    status TEXT NOT NULL,          -- pending|started|scanning|review|done|error
    task_id TEXT,                  -- Celery task UUID (Phase 4)
    config_json TEXT,              -- JSON serialized BatchConfig
    findings_json TEXT,            -- JSON serialized list of findings
    metadata_json TEXT,            -- Additional metadata
    error_message TEXT,            -- Error details if status=error
    ttl_expires_at TIMESTAMP       -- Auto-cleanup timestamp
);

CREATE INDEX idx_task_id ON batches(task_id);
CREATE INDEX idx_status ON batches(status);
CREATE INDEX idx_ttl ON batches(ttl_expires_at);
```

---

**Last Updated:** 2026-03-02 (Phase 4)  
**Version:** 4.1.0
