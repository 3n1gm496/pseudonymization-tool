# UX Flow e Wireframe Concettuali

**Autore:** Manus AI
**Versione:** 1.0 (MVP)
**Data:** 2026-02-25

---

## 1. Panoramica del Flusso Utente

L'esperienza utente è progettata per essere lineare e guidata, riducendo al minimo l'ambiguità per l'operatore tecnico. Il flusso si articola in quattro passaggi principali, ospitati in una singola pagina web (SPA) che aggiorna dinamicamente la sua vista.

1.  **Configurazione e Upload:** L'utente imposta i parametri del batch e carica i file.
2.  **Scansione e Attesa:** Il sistema processa i file e l'utente attende il completamento.
3.  **Review e Decisione:** L'utente analizza i risultati e prende decisioni su ogni entità trovata.
4.  **Finalizzazione e Download:** L'utente applica le modifiche e scarica gli artefatti finali.

## 2. Wireframe Concettuali e Passaggi Dettagliati

Di seguito sono descritte le schermate principali dell'interfaccia utente.

### Schermata 1: Pagina di Avvio (Stato Iniziale)

**Descrizione:** È la prima vista che l'utente incontra. È pulita e focalizzata sull'azione principale: iniziare un nuovo batch.

**Componenti:**
- **Area Drag & Drop:** Un'ampia zona centrale invita l'utente a trascinare i file o a cliccare per selezionarli dal filesystem.
- **Opzioni di Configurazione:**
    - **Selettore Modalità:** Un radio button o toggle per scegliere tra `Light` e `Strict` (default: `Light`).
    - **Campo Passphrase:** Un campo di testo per inserire la passphrase per la cifratura del mapping. Un'icona permette di visualizzare la password.
    - **Checkbox Dry-Run:** Una casella di controllo per attivare la modalità di sola scansione.
- **Pulsante di Azione:** Un pulsante "Avvia Scansione", disabilitato finché non viene caricato almeno un file e inserita una passphrase.

**Wireframe Concettuale:**
```
+--------------------------------------------------------------------+
|                      Local Pseudonymization Tool                   |
+--------------------------------------------------------------------+
|                                                                    |
|   +------------------------------------------------------------+   |
|   |                                                            |   |
|   |          Trascina qui i file o clicca per caricare         |   |
|   |                                                            |   |
|   +------------------------------------------------------------+   |
|                                                                    |
|   File caricati: (nessuno)                                         |
|                                                                    |
|   ---------------------------------------------------------------- |
|                                                                    |
|   Modalità:  (o) Light   ( ) Strict                              |
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
