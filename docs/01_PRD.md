# Product Requirements Document (PRD) — Local Pseudonymization Tool

Local anonymization tool for secure data processing before AI analysis.

---

## 1. Visione e Obiettivo

L'obiettivo di questo progetto è creare un **tool di pseudonimizzazione locale, sicuro e affidabile**, destinato a utenti tecnici in ambienti sensibili come **Security Operations Center (SOC)** e **Amministrazioni Pubbliche**. Il tool permetterà di preparare contenuti (documenti, log, immagini) per l'analisi tramite servizi AI cloud, garantendo che nessun dato sensibile o identificativo venga divulgato all'esterno del perimetro locale.

Il prodotto finale sarà una **web application standalone** che opera esclusivamente sul PC dell'utente (`localhost`), senza effettuare alcuna chiamata di rete, garantendo privacy e sicurezza by-design.

## 2. Target Audience

L'utente tipo è un **operatore tecnico** con le seguenti caratteristiche:

- **Ruolo:** Analista SOC, System Administrator, Digital Forensics and Incident Response (DFIR) analyst.
- **Esigenze:** Necessità di sfruttare le capacità di modelli AI cloud per analisi di sicurezza, redazione di policy, o indagini, senza esporre dati confidenziali dell'organizzazione o dei cittadini.
- **Competenze:** A suo agio con strumenti locali, terminale e concetti di sicurezza informatica. Non richiede un'esperienza utente consumer, ma apprezza un workflow chiaro, robusto e trasparente.

## 3. Requisiti di Prodotto (MVP)

### 3.1. Funzionalità Chiave

| Funzionalità | Descrizione |
|---|---|
| **Input File** | L'utente può caricare file singoli o in batch tramite un'interfaccia di drag & drop. |
| **Formati Supportati** | Il tool deve processare i seguenti formati: `txt`, `md`, `csv`, `docx`, `pdf` (solo testuali), `xlsx` (solo celle di testo, formule ignorate), `jpg`, `png`. |
| **OCR Locale per Immagini** | Per `jpg` e `png`, il tool deve eseguire un OCR locale offline per estrarre il testo, permettere la redazione visuale delle aree sensibili (tramite box di oscuramento) e rimuovere i metadati EXIF. |
| **Modalità di Pseudonimizzazione** | L'utente può scegliere tra due profili: **Light** (preserva il contesto e la struttura dei dati per massimizzare l'utilità analitica) e **Strict** (massimizza l'offuscamento per ridurre al minimo il rischio di re-identificazione). |
| **Modalità Dry-Run** | L'utente può eseguire una scansione in modalità "dry-run" per visualizzare le entità che verrebbero pseudonimizzate senza applicare alcuna modifica. |
| **Review Manuale** | Un'interfaccia dedicata permette all'utente di revisionare tutte le entità rilevate prima di applicare le trasformazioni. L'utente può accettare, modificare, o escludere ogni singolo finding. |
| **Consistenza e Reversibilità** | La pseudonimizzazione è **consistente** all'interno di un singolo batch (stesso input -> stesso output). È **reversibile** tramite un file di mapping generato per ogni batch e cifrato con una passphrase fornita dall'utente. |
| **Output** | Al termine del processo, l'utente può scaricare i file pseudonimizzati, un report finale (formati JSON e HTML) e il file di mapping cifrato. |

### 3.2. Entità da Rilevare (MVP)

Il sistema deve essere in grado di rilevare e pseudonimizzare le seguenti categorie di dati, con un focus sul contesto italiano:

- **Dati Personali e Contatti:** Nomi e cognomi, indirizzi email, numeri di telefono.
- **Identificativi Fiscali:** Codice Fiscale, Partita IVA.
- **Dati di Rete e Sistema:** Indirizzi IP (IPv4 e IPv6 best-effort), URL, nomi a dominio (FQDN), hostname, username/utenze.
- **Pattern Custom:** Il tool deve supportare dizionari e pattern regex configurabili dall'utente per rilevare terminologia interna specifica (es. nomi di server, codici progetto, sigle di uffici).

### 3.3. Requisiti Non Funzionali (Vincolanti)

| Requisito | Descrizione |
|---|---|
| **Sicurezza (Offline)** | L'applicazione non deve effettuare **nessuna chiamata di rete** a servizi esterni durante l'elaborazione. Il server web locale deve essere in ascolto solo su `127.0.0.1`. |
| **Privacy by Design** | I log applicativi non devono contenere dati sensibili originali. I file temporanei devono essere gestiti in una directory dedicata e rimossi al termine di ogni operazione. |
| **Trasparenza** | L'utente deve essere informato con messaggi chiari ed espliciti in caso di errori, file non processabili (es. PDF cifrati, OCR fallito), o limiti noti. |
| **Robustezza** | Il tool deve avere un comportamento fail-safe: in caso di fallimento di un modulo, il file corrispondente non deve mai essere dichiarato "safe" senza un warning evidente. |

## 4. User Experience (UX) Flow - MVP

1.  **Avvio:** L'utente avvia l'applicazione tramite uno script locale (`.bat`/`.sh`), che apre automaticamente l'interfaccia web nel browser.
2.  **Upload:** L'utente trascina uno o più file nell'area di upload.
3.  **Configurazione Batch:** L'utente seleziona la modalità (`Light`/`Strict`) e inserisce una passphrase per cifrare il mapping di reversibilità.
4.  **Scansione:** L'utente avvia la scansione (normale o dry-run).
5.  **Review:** L'applicazione presenta una lista di tutte le entità sensibili trovate, raggruppate per tipo e file di origine. Per ogni entità, vengono mostrati il valore originale, lo pseudonimo proposto e un punteggio di confidenza. L'utente può approvare, modificare o ignorare ogni suggerimento.
6.  **Applicazione:** L'utente conferma le modifiche. Il backend processa i file e applica la pseudonimizzazione.
7.  **Download:** L'interfaccia presenta i link per scaricare l'archivio con i file processati, il report di riepilogo e il file `.enc` del mapping cifrato.

## 5. Stack Tecnologico (Proposto)

- **Backend:** Python 3.11+ con **FastAPI**.
- **Frontend:** **HTML5, CSS3, JavaScript (Vanilla)** per massimizzare la compatibilità e minimizzare le dipendenze esterne.
- **Librerie Chiave:**
    - OCR: **Tesseract** (tramite wrapper Python).
    - Parsing Documenti: `python-docx`, `openpyxl`, `pypdf`.
    - Cifratura: `cryptography`.
- **Deployment:** Script di avvio (`.bat` per Windows, `.sh` per Linux/macOS) che installa le dipendenze in un ambiente virtuale e avvia il server Uvicorn.

## 6. Non-Obiettivi (Cosa non faremo nel MVP)

- Supporto per OCR su PDF scansionati.
- Integrazione di modelli di Natural Language Processing (NLP/NER) locali.
- Autenticazione utente o gestione multi-utente.
- Funzionalità SaaS o cloud-based.
- Installer nativi per sistemi operativi (es. MSI, DMG).
- Confronto visuale affiancato (side-by-side) del prima/dopo.
