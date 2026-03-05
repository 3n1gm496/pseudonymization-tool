# Roadmap — Local Pseudonymization Tool

**Versione:** 5.2.1
**Data:** 2026-03-05

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

| Funzionalità | Stato | Descrizione | Obiettivo Principale |
|---|---|---|---|
| **OCR su PDF Scansionati** | ✅ Implementato | Pipeline che estrae le immagini dai PDF e applica l'OCR su di esse (`image_parser.py`). | Estendere il supporto a una vasta categoria di documenti comuni in ambito PA e legale. |
| **NER Locale (CPU-Friendly)** | ✅ Implementato (v5.2.x) | Modello spaCy (`MLNERDetector`) per rilevare nomi di persona, organizzazioni e luoghi. Protetto da circuit breaker. | Aumentare l'accuratezza del rilevamento per i dati non strutturati. |
| **Detector Paralleli** | ✅ Implementato (v5.2.1) | `ThreadPoolExecutor` nel `PseudonymizationEngine` — detector lenti non bloccano quelli veloci. | Riduzione latenza stimata 40-60% su testi multi-detector. |
| **Circuit Breaker Detector Esterni** | ✅ Implementato (v5.2.1) | LDAP e ML protetti da circuit breaker; fallback graceful in caso di indisponibilità. | Alta disponibilità del pipeline indipendentemente dai servizi esterni. |
| **Pseudonimizzazione Format-Preserving Avanzata** | 📋 Backlog | Tecniche che preservano il formato originale (es. IP→IP fittizio valido). | Migliorare l'utilità dei dati pseudonimizzati per strumenti di analisi. |
| **Installer Windows Nativo** | 📋 Backlog | Installer `.msi` / `.exe` per ambienti Windows restrittivi. | Ridurre la barriera all'adozione. |
| **Profili di Configurazione Custom** | 📋 Backlog | Salvataggio e caricamento di preset di configurazione per casi d'uso ricorrenti. | Migliorare l'efficienza per compiti ripetitivi. |

## 4. Fase Futura: Funzionalità Avanzate e Integrazioni

Questa fase esplora funzionalità più sofisticate e l'integrazione con l'ecosistema di sicurezza esistente.

| Funzionalità | Descrizione | Obiettivo Principale |
|---|---|---|
| **Detector SOC Avanzati** | Sviluppare o integrare detector specifici per il dominio della sicurezza informatica (es. riconoscere specifici formati di log, identificatori di minacce, etc.). | Aumentare il valore del tool per i casi d'uso di indagine e threat intelligence. |
| **Integrazione con Vault di Segreti** | Permettere al tool di recuperare la passphrase da un vault di segreti locale (es. KeePass, HashiCorp Vault) invece di richiederla all'utente. | Migliorare la sicurezza operativa e la gestione delle credenziali. |
| **Modalità di Anonimizzazione Irreversibile** | Aggiungere un'opzione per eseguire un'anonimizzazione irreversibile (one-way) utilizzando funzioni di hash con salt, per i casi in cui la reversibilità non è necessaria o desiderata. | Fornire una maggiore flessibilità in base ai requisiti di data privacy. |
| **Dashboard e Statistiche Avanzate** | Creare una dashboard che mostri statistiche aggregate sull'utilizzo del tool nel tempo (es. tipi di entità più comuni, volumi di dati processati). | Fornire insight operativi ai team che utilizzano il tool. |
| **Plugin per Applicazioni Esterne** | Sviluppare plugin o integrazioni per consentire la pseudonimizzazione direttamente da altre applicazioni (es. un add-in per un client di posta elettronica o un editor di testo). | Integrare la pseudonimizzazione in modo più trasparente nel workflow quotidiano degli utenti. |
