> **Nota importante:** Questo è un fork del README originale, aggiornato per la versione `1.0.3` con fix specifici per Windows e una procedura di installazione offline.

# Local Pseudonymization Tool — MVP v1.0.3

Questo tool è una web app locale (localhost) per la pseudonimizzazione di dati sensibili in documenti di testo, DOCX, XLSX, PDF e immagini. È progettato per essere eseguito in ambienti sicuri senza accesso a internet, garantendo che nessun dato lasci mai la macchina dell'utente.

**Caratteristiche principali:**
- **100% Offline**: Nessuna chiamata di rete esterna.
- **Supporto multiformato**: TXT, CSV, MD, DOCX, XLSX, PDF (testuali), JPG, PNG.
- **Sicurezza**: Mapping cifrato con passphrase, nessun dato sensibile nei log o nei report.
- **Flessibilità**: Modalità `light` (solo entità di rete) e `strict` (tutte le entità).
- **Review manuale**: Possibilità di rivedere e approvare/rifiutare ogni pseudonimo proposto.

---

## 1. Prerequisiti

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

## 2. Installazione e Avvio

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

---

## 3. Come Usare l'Applicazione

1. **Upload**: Trascina i file da processare nell'area di upload.
2. **Configura**: Seleziona la modalità (`light` o `strict`) e inserisci una **passphrase robusta** (essenziale per la sicurezza del mapping).
3. **Avvia Scansione**: Il backend analizza i file e rileva le entità sensibili.
4. **Review**: Rivedi i "finding" proposti. Puoi deselezionare quelli che non vuoi pseudonimizzare.
5. **Applica**: Applica le modifiche. I file originali non vengono mai toccati.
6. **Download**: Scarica un file ZIP contenente:
   - `files/`: i documenti pseudonimizzati.
   - `report.html`: un report navigabile dei finding e delle sostituzioni.
   - `report.json`: i dati grezzi del report.
   - `mapping.enc`: il file di mapping **cifrato** con la tua passphrase. **Conservalo** per garantire la consistenza tra diversi batch.

---

## 4. Sicurezza e Limitazioni

- **Passphrase**: La sicurezza del mapping dipende dalla robustezza della passphrase. Usane una lunga e complessa.
- **OCR**: La qualità dell'OCR dipende dalla risoluzione e dalla chiarezza dell'immagine. Testo sfocato o scritto a mano potrebbe non essere rilevato.
- **Formule XLSX**: Le formule vengono ignorate e non pseudonimizzate per evitare di corrompere i fogli di calcolo.
- **Log di Installazione**: In caso di problemi durante l'installazione delle dipendenze, il log completo viene salvato in `install.log`.
