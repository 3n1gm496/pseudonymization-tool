# UX Flow e User Journey

**Autore:** Team Engineering
**Versione:** 5.0.0
**Data:** 2026-03-02

---

## Overview

L'esperienza utente è progettata come un **workflow lineare a 3 fasi** con una **sezione opzionale di reversione**.

### Fasi Principali

1. **Scan Phase** — Upload file/testo, avvio scansione (preset `SOC Logs` applicato automaticamente)
2. **Review Phase** — Revisione dei finding, personalizzazione pseudonimi
3. **Results Phase** — Download dei file, accesso a passphrase e mapping
4. **Revert Panel (Opzionale)** — Decifrare risposte AI o reversi batch precedenti

---

## Phase 4: Async UX Pattern

**Background Processing with Polling**

Con l'architettura asincrona (Phase 4), le scansioni di lunga durata vengono eseguite in background, garantendo che l'interfaccia rimanga responsiva e l'utente riceva feedback visivo sul progresso.

### Async Flow Diagram

```
User clicks "Scan"
       ↓
POST /api/batches → 202 Accepted + task_id
       ↓
Frontend: "Scan in coda..."
       ↓
[Polling Loop - every 2 seconds]
GET /api/batches/{id}/status
       ↓
┌──────────────────────────────────────────┐
│  Status: PENDING                         │
│  UI: "⏳ Scan in coda, attendere..."    │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  Status: STARTED                         │
│  UI: "▶️ Scansione in corso... 0%"      │
└──────────────────────────────────────────┘
       ↓ (optional progress updates)
┌──────────────────────────────────────────┐
│  Status: PROGRESS                        │
│  Progress: 45%                           │
│  UI: "▶️ Scansione in corso... 45%"     │
│  Current: "Processing document3.pdf..."  │
└──────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│  Status: SUCCESS                         │
│  UI: "✅ Scansione completata!"         │
│  Result: {findings: 42, files: 5}       │
│  → Auto-switch to Review tab             │
└──────────────────────────────────────────┘
       OR (error case)
┌──────────────────────────────────────────┐
│  Status: FAILURE                         │
│  UI: "❌ Errore: {error_message}"       │
│  → Show error toast + stay on Scan tab  │
└──────────────────────────────────────────┘
```

### UI Components (Phase 4)

**Progress Indicator:**
```jsx
// Scan in corso
<div className="progress-container">
  <div className="spinner"></div>
  <p>Scansione in corso... {progress}%</p>
  {currentFile && <small>Processing: {currentFile}</small>}
</div>
```

**Status Badge:**
```jsx
{status === "pending" && <Badge color="gray">In coda</Badge>}
{status === "started" && <Badge color="blue">In corso</Badge>}
{status === "success" && <Badge color="green">Completato</Badge>}
{status === "failed" && <Badge color="red">Errore</Badge>}
```

**Polling Implementation (Frontend):**
```javascript
async function pollBatchStatus(batchId) {
  const maxAttempts = 300; // 10 minutes (2s interval)
  let attempts = 0;
  
  const interval = setInterval(async () => {
    try {
      const response = await fetch(`/api/batches/${batchId}/status`);
      const data = await response.json();
      
      // Update UI with progress
      setProgress(data.progress || 0);
      setStatus(data.status);
      setCurrentFile(data.current_file);
      
      // Check if completed
      if (data.status === "completed") {
        clearInterval(interval);
        showToast("Scansione completata!", "success");
        switchToReviewTab();
      } else if (data.status === "failed") {
        clearInterval(interval);
        showToast(`Errore: ${data.error}`, "error");
      }
      
      // Timeout safeguard
      if (++attempts >= maxAttempts) {
        clearInterval(interval);
        showToast("Timeout: scansione troppo lunga", "warning");
      }
    } catch (error) {
      console.error("Polling error:", error);
    }
  }, 2000); // Poll every 2 seconds
}
```

**User Feedback:**
- **Pending**: Spinner + "Scan in coda, attendere..."
- **Started**: Progress bar + percentage + current file
- **Success**: Checkmark + "Completato!" + auto-navigate to Review
- **Failure**: Error icon + error message + "Riprova" button

---

## Flusso Dettagliato

### FASE 1: SCAN (Scanner Component)

**Stato iniziale:**
- Tre tab: **Scanner**, **Review**, **Results** 
- Di default aperto: **Scanner** tab
- Lo scanner rimane disponibile durante tutte le fasi

**Componenti visibili:**
```
┌─────────────────────────────────────────────────┐
│         Modalità Input (Radio Selection)        │
│  ( ) Text Input    (o) File Upload             │
└─────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ SELECT POLICY (Policy Selector Component)       │
│                                                │
│ Preset: [SOC Logs ▼]                          │
│                                                │
│ Preview delle entità che saranno scansionate   │
│ - HOSTNAME, IPV4, EMAIL, CUSTOM_CODES, ...    │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ DETTAGLI BATCH (Readonly Info)                 │
│                                                │
│ Batch ID: [abc123...def789] (truncated)       │
│ Safety Label: MEDIUM                           │
│ Created: 2026-03-02T10:30:00                   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ FILE/TEXT INPUT AREA                           │
│                                                │
│ IF TEXT MODE:                                  │
│   [Large textarea for pasting text]            │
│   Placeholder: "Incolla testo..."              │
│                                                │
│ IF FILE MODE:                                  │
│   [Drag & drop zone]                           │
│   Oppure [Click to browse]                     │
│   Supported: TXT, CSV, MD, DOCX, XLSX, PDF,.. │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ PASSPHRASE & SCAN CONTROLS                     │
│                                                │
│ Passphrase: [________________] [👁] [👁]       │
│                                                │
│ [🔍 Scan] [🔄 Clear]                          │
└──────────────────────────────────────────────────┘

│ [ℹ️ Spinner mentre processa]                  │
```

**Flusso:**
1. User seleziona modalità (text/file)
2. User inserisce passphrase (preset `SOC Logs` fisso — nessuna selezione richiesta)
3. User carica testo/file
4. User clicca "Scan" → va a Review tab automaticamente

---

### FASE 2: REVIEW (FindingsTable + Results Preview)

**Tab automaticamente attivato** dopo scan completato.

**Componenti:**
```
┌────────────────────────────────────────────┐
│ FINDINGS SUMMARY                          │
│ Entities scanned: 42 | Unique: 28        │
│ Safety Label: SENSITIVE                   │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ FILTRI & SEARCH                           │
│ [Entity Type ▼] [File ▼] [Confidence ▼]   │
│ Search: [____________]                    │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│ FINDINGS TABLE (Scrollable)                                   │
├─────────────────────────────────────────────────────────────┤
│ Entity      Original          Pseudonym    Source    Conf. ✓ │
├─────────────────────────────────────────────────────────────┤
│ EMAIL       mario@acme.com    EMAIL_001    file.txt  0.95[✓] │
│ IPV4        10.0.0.1          IPV4_001     logs.pdf  1.00[✓] │
│ HOSTNAME    server.acme.com   HOST_001     email     0.87[ ] │
│ ...                                                          │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ PSEUDONYM CUSTOMIZATION (On Row Select)    │
│                                            │
│ Original: mario@acme.com                   │
│ Current Pseudonym: [EMAIL_001________]     │
│ [Update]                                   │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ ACTION BUTTONS                             │
│ [Apply All] [Reset] [Download Report]     │
└────────────────────────────────────────────┘
```

**Interazioni:**
- Click row → edita pseudonimo
- Checkbox per include/exclude entità
- "Apply All" → genera pseudo, va a Results

---

### FASE 3: RESULTS (Passphrase + Mapping + Downloads)

**Tab automaticamente attivato** dopo Apply.

**Layout:**
```
┌──────────────────────────────────────────────────┐
│ PSEUDONYMIZED OUTPUT SECTION                    │
│                                                 │
│ IF TEXT INPUT:                                  │
│   │ User EMAIL_001 created CUSTOM_001          │
│   │ on IPV4_001 at 2026-02...                  │
│   │                                             │
│   [Copy] [Download TXT]                        │
│                                                 │
│ IF FILE INPUT:                                  │
│   ✓ Scanned 5 files → Pseudonymized 3         │
│   [Download ZIP] [Download Report HTML]       │
│                                                 │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ 🔐 PASSPHRASE & MAPPING CIFRATO                │
│                                                 │
│ Passphrase (per decifrazione):                │
│ [••••••••••••••••] [👁] [Copy] [Show]         │
│                                                 │
│ File di Mapping Cifrato:                       │
│ mapping_abc123.enc (stored securely)           │
│ ✓ Download mapping.enc                        │
│                                                 │
│ ⚠️ Conserva entrambi per decifrazione risposte │
│                                                 │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ STATS & METADATA                               │
│ Batch ID: abc123...def789                      │
│ Pseudonymized Entities: 28                     │
│ Safety Label: SENSITIVE                        │
│ Processed at: 2026-03-02T10:35:00              │
└──────────────────────────────────────────────────┘

[New Scan] [Download Report]
```

---

### FASE 4 (OPZIONALE): REVERT PANEL

**Accessibile da sidebar/drawer**, quando user ha mapping.enc + passphrase.

**TAB 1: Decifra Risposta AI**
```
┌──────────────────────────────────────────┐
│ Upload Mapping File                     │
│ [Choose mapping_abc.enc...]             │
│                                         │
│ Enter Passphrase:                       │
│ [________________] [👁]                 │
│                                         │
│ Paste AI Response:                      │
│ [Large textarea]                        │
│                                         │
│ [Preview Decryption]                    │
│ Matches found: 3/3 ✓                    │
│                                         │
│ [Apply Decryption] → Download           │
└──────────────────────────────────────────┘
```

**TAB 2: Revert Batch ZIP**
```
┌──────────────────────────────────────────┐
│ Upload Previous Batch ZIP                │
│ [Choose batch-abc123.zip...]             │
│                                         │
│ Enter Passphrase:                       │
│ [________________] [👁]                 │
│                                         │
│ [Preview Revert]                        │
│ Files to revert: 5                      │
│ Mapping entries: 28                     │
│                                         │
│ [Apply Revert] → Download reverted ZIP  │
└──────────────────────────────────────────┘
```

---

## State Management

**Scanner → Review → Results flussi:**
- Scanner: Colleziona file + passphrase → /api/batches POST (preset `SOC Logs` come default fisso)
- Review: Mostra findings da batch → /api/findings GET
- Results: Mostra output + mapping + passphrase (in frontend state)

**Revert Panel flussi:**
- Decifra: Upload .enc + passphrase → /api/revert/decipher
- Revert Zip: Upload ZIP + .enc + passphrase → /api/revert/batch

---

## Accessibility Notes

✅ ARIA labels su tutti i tab  
✅ Keyboard navigation (Tab, Enter)  
✅ Dark mode con sufficiente contrast  
✅ Toast notifications per feedback (success, error, warning)
|                                                                    |
|   Passphrase: [___________________________________________] [👁]   |
|                                                                    |
|   [ ] Esegui come Dry-Run (sola analisi)                           |
|                                                                    |
|   +------------------------------------------------------------+   |
|   |                     [ Avvia Scansione ]                    |   |
|   +------------------------------------------------------------+   |
|                                                                    |
+--------------------------------------------------------------------+
```

### Schermata 2: In Corso di Processamento

**Descrizione:** Una vista di attesa che fornisce un feedback visivo mentre il backend processa i file.

**Componenti:**
- **Barra di Progresso:** Una barra di progresso indica l'avanzamento complessivo del batch.
- **Log di Stato:** Un'area di testo mostra lo stato corrente (es. "Parsing file `log.txt`...", "Esecuzione OCR su `screenshot.png`...").
- **Pulsante Annulla:** Un pulsante per interrompere il processo.

### Schermata 3: Review Manuale

**Descrizione:** È la schermata più importante, dove l'utente ha il pieno controllo sulle modifiche da applicare. La vista è dominata da una tabella con tutte le entità trovate.

**Componenti:**
- **Tabella dei Findings:** Una tabella scrollabile e filtrabile con le seguenti colonne:
    - **Tipo Entità:** (es. `EMAIL`, `IPV4`)
    - **Valore Originale:** Il testo sensibile trovato.
    - **Pseudonimo Proposto:** Lo pseudonimo generato dal sistema.
    - **File / Posizione:** Il file e la riga/sezione dove è stato trovato.
    - **Confidenza:** Il punteggio di confidenza del detector.
    - **Azione:** Un menu a tendina per ogni riga con le opzioni: `Accetta`, `Escludi`, `Modifica`.
- **Filtri:** Controlli per filtrare la tabella per tipo di entità, file o livello di confidenza.
- **Azioni Globali:** Pulsanti per "Accetta Tutti" o "Escludi Tutti".
- **Pulsante di Finalizzazione:** Un pulsante "Applica Modifiche e Genera Output" che si attiva solo dopo che l'utente ha interagito con la schermata (per evitare conferme accidentali).

**Wireframe Concettuale (Tabella):**
```
+--------------------------------------------------------------------------------------------------------------------+
|                                             Schermata di Review (Batch: 123e4567)                                  |
+--------------------------------------------------------------------------------------------------------------------+
| Filtri: [Tipo Entità v] [File v] [Confidenza v]                                                                    |
+--------------------------------------------------------------------------------------------------------------------+
| | Tipo   | Valore Originale          | Pseudonimo Proposto         | Sorgente         | Conf. | Azione            | |
|--------------------------------------------------------------------------------------------------------------------|
| | EMAIL  | mario.rossi@ente.gov.it   | user_001@orgdom_001.gov.it  | report.docx:15   | 0.95  | [ Accetta    v ]  | |
| | IPV4   | 10.24.8.15                | IPV4_SUBNET_001_HOST_001    | logs.txt:101     | 1.00  | [ Accetta    v ]  | |
| | PERSON | Mario Rossi               | PERSON_001                  | report.docx:12   | 0.80  | [ Escludi    v ]  | |
| ...                                                                                                                |
+--------------------------------------------------------------------------------------------------------------------+
|                                                                                                                    |
|   +-----------------------------------------------------------+    +---------------------------------------------+   |
|   |            [ Applica Modifiche e Genera Output ]          |    |                [ Annulla Batch ]            |   |
|   +-----------------------------------------------------------+    +---------------------------------------------+   |
|                                                                                                                    |
+--------------------------------------------------------------------------------------------------------------------+
```

### Schermata 4: Completato e Download

**Descrizione:** La vista finale che conferma il completamento del processo e fornisce i link per il download degli artefatti.

**Componenti:**
- **Messaggio di Successo:** Un messaggio chiaro che indica che il batch è stato processato con successo.
- **Riepilogo:** Un breve riassunto (es. "Processati 5 file, 42 entità pseudonimizzate").
- **Link di Download:**
    - Pulsante "Scarica File Pseudonimizzati (.zip)"
    - Pulsante "Scarica Report (HTML)"
    - Pulsante "Scarica Report (JSON)"
    - Pulsante "Scarica Mappa Cifrata (.enc)"
- **Pulsante "Nuovo Batch":** Per tornare alla schermata iniziale e ricominciare.
