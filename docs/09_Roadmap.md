# Roadmap — Local Pseudonymization Tool

**Autore:** Manus AI
**Versione:** 4.0.4
**Data:** 2026-03-02

---

## 1. Introduzione

Questo documento delinea la visione a lungo termine per l'evoluzione del Local Pseudonymization Tool, andando oltre la versione MVP (Minimum Viable Product). La roadmap è suddivisa in fasi successive, ognuna delle quali introduce nuove capacità e miglioramenti in base al feedback degli utenti e alle esigenze emergenti.

## 2. Versione MVP (Baseline)

La versione iniziale si concentra sulla fornitura di un tool funzionale, sicuro e robusto che copre i casi d'uso più critici per gli analisti SOC e gli amministratori di sistema. Le funzionalità principali includono:

- Supporto per formati di file chiave (testo, documenti, immagini).
- OCR locale per immagini con redazione visuale.
- Pseudonimizzazione consistente e reversibile basata su policy Light/Strict.
- Workflow completo con review manuale.
- Sicurezza by-design con operatività completamente offline.

## 3. Fase Successiva: Hardening e Usabilità

Questa fase si concentra sul miglioramento della robustezza, dell'usabilità e della copertura del tool.

| Funzionalità | Descrizione | Obiettivo Principale |
|---|---|---|
| **OCR su PDF Scansionati** | Integrare una pipeline che estrae le immagini dai PDF e applica l'OCR su di esse. | Estendere il supporto a una vasta categoria di documenti comuni in ambito PA e legale. |
| **NER Locale (CPU-Friendly)** | Integrare un modello di Natural Language Processing (es. `spaCy`) per migliorare il rilevamento di entità come nomi di persona e organizzazioni, riducendo i falsi negativi. | Aumentare l'accuratezza del rilevamento per i dati non strutturati. |
| **Pseudonimizzazione Format-Preserving Avanzata** | Implementare tecniche di pseudonimizzazione che preservano il formato originale in modo più realistico (es. un indirizzo IP viene sostituito con un altro IP valido ma fittizio). | Migliorare l'utilità dei dati pseudonimizzati per gli strumenti di analisi che si aspettano formati specifici. |
| **Installer Windows Nativo** | Creare un installer `.msi` (usando WiX Toolset) o `.exe` (usando Inno Setup/NSIS) per semplificare drasticamente il processo di installazione per gli utenti Windows. | Ridurre la barriera all'adozione e i ticket di supporto legati all'installazione. |
| **Profili di Configurazione Custom** | Permettere agli utenti di salvare e caricare set di configurazioni (modalità, dizionari attivi, etc.) per diversi casi d'uso. | Migliorare l'efficienza per gli utenti che eseguono compiti ripetitivi. |

## 4. Fase Futura: Funzionalità Avanzate e Integrazioni

Questa fase esplora funzionalità più sofisticate e l'integrazione con l'ecosistema di sicurezza esistente.

| Funzionalità | Descrizione | Obiettivo Principale |
|---|---|---|
| **Detector SOC Avanzati** | Sviluppare o integrare detector specifici per il dominio della sicurezza informatica (es. riconoscere specifici formati di log, identificatori di minacce, etc.). | Aumentare il valore del tool per i casi d'uso di indagine e threat intelligence. |
| **Integrazione con Vault di Segreti** | Permettere al tool di recuperare la passphrase da un vault di segreti locale (es. KeePass, HashiCorp Vault) invece di richiederla all'utente. | Migliorare la sicurezza operativa e la gestione delle credenziali. |
| **Modalità di Anonimizzazione Irreversibile** | Aggiungere un'opzione per eseguire un'anonimizzazione irreversibile (one-way) utilizzando funzioni di hash con salt, per i casi in cui la reversibilità non è necessaria o desiderata. | Fornire una maggiore flessibilità in base ai requisiti di data privacy. |
| **Dashboard e Statistiche Avanzate** | Creare una dashboard che mostri statistiche aggregate sull'utilizzo del tool nel tempo (es. tipi di entità più comuni, volumi di dati processati). | Fornire insight operativi ai team che utilizzano il tool. |
| **Plugin per Applicazioni Esterne** | Sviluppare plugin o integrazioni per consentire la pseudonimizzazione direttamente da altre applicazioni (es. un add-in per un client di posta elettronica o un editor di testo). | Integrare la pseudonimizzazione in modo più trasparente nel workflow quotidiano degli utenti. |
