# Rischi e Mitigazioni

**Versione:** 5.2.1
**Data:** 2026-03-05

---

## 1. Introduzione

Questo documento identifica i potenziali rischi tecnici, di progetto e di sicurezza che potrebbero impattare lo sviluppo e l'adozione del Local Pseudonymization Tool. Per ogni rischio, viene proposta una strategia di mitigazione per ridurne la probabilità o l'impatto.

## 2. Tabella dei Rischi

I rischi sono classificati per categoria e valutati in termini di probabilità e impatto (Alto, Medio, Basso).

### Categoria: Rischi Tecnici

| Rischio | Probabilità | Impatto | Descrizione | Strategia di Mitigazione |
|---|---|---|---|---|
| **Scarsa qualità dell'OCR** | Alta | Medio | L'OCR locale (Tesseract) potrebbe non riuscire a estrarre correttamente il testo da immagini di bassa qualità, screenshot complessi o con font non standard, portando a falsi negativi (dati sensibili non rilevati). | 1. **Trasparenza:** Informare chiaramente l'utente sui limiti dell'OCR. 2. **Warning Espliciti:** Se il motore OCR restituisce una confidenza bassa, marcare il file come "parzialmente processato" e inserire un warning prominente nel report. 3. **Guida Utente:** Fornire raccomandazioni su come produrre screenshot più "OCR-friendly". |
| **Complessità del parsing dei file** | Media | Alto | I formati come `.docx` e `.xlsx` sono complessi. La libreria di parsing potrebbe non gestire correttamente elementi specifici (es. commenti, note a piè di pagina, macro), lasciando dati sensibili non processati. | 1. **Scope Limitato:** Per l'MVP, dichiarare esplicitamente che verranno processati solo i contenuti testuali principali. 2. **Librerie Robuste:** Utilizzare librerie consolidate e ben mantenute (`python-docx`, `openpyxl`). 3. **Warning:** Segnalare nel report ogni elemento del documento che non è stato possibile analizzare. |
| **Performance Lente** | Bassa | Medio | L'elaborazione di batch di grandi dimensioni o di file molto grandi, specialmente se richiedono OCR, potrebbe risultare lenta e impattare negativamente l'esperienza utente. | ✅ **Mitigato (v5.2.1):** 1. **Celery Asincrono:** L'elaborazione è delegata a worker Celery, il frontend riceve aggiornamenti via SSE. 2. **Detector Paralleli:** `ThreadPoolExecutor` esegue i detector in parallelo (riduzione stimata 40-60% sui testi multi-detector). 3. **Metriche:** Prometheus histograms (`detector_duration_seconds`, `file_processing_seconds`) per identificare i colli di bottiglia. |

### Categoria: Rischi di Sicurezza

| Rischio | Probabilità | Impatto | Descrizione | Strategia di Mitigazione |
|---|---|---|---|---|
| **Dati sensibili lasciati su disco** | Bassa | Alto | Bug nel processo di pulizia o un crash imprevisto potrebbero lasciare file originali o intermedi non cifrati nella directory temporanea. | 1. **Cleanup Robusto:** Implementare la logica di pulizia in un blocco `finally` per garantirne l'esecuzione anche in caso di eccezioni. 2. **Directory Dedicata:** Usare una directory temporanea specifica per ogni batch, rendendo più semplice la sua identificazione e rimozione. 3. **Raccomandazioni Operative:** Suggerire nel README l'uso del tool su macchine con crittografia del disco (es. BitLocker). |
| **Vulnerabilità in una dipendenza** | Media | Alto | Una delle librerie di terze parti utilizzate (es. FastAPI, `pypdf`) potrebbe avere una vulnerabilità di sicurezza non nota. | 1. **Minimizzare le Dipendenze:** Usare solo le librerie strettamente necessarie. 2. **Pinning delle Versioni:** Fissare le versioni delle dipendenze nel file `requirements.txt` a versioni note e stabili. 3. **Nessuna Esposizione di Rete:** Il binding del server solo su `127.0.0.1` riduce drasticamente la superficie di attacco, impedendo lo sfruttamento di eventuali vulnerabilità di rete da parte di attori esterni. |
| **Passphrase debole** | Alta | Medio | L'utente potrebbe scegliere una passphrase debole, rendendo il file di mapping vulnerabile ad attacchi di forza bruta offline. | 1. **Indicatore di Robustezza:** Implementare un semplice indicatore visivo della robustezza della passphrase nell'interfaccia utente. 2. **Raccomandazioni:** Mostrare un avviso che incoraggia l'uso di passphrase lunghe e complesse. 3. **Algoritmo Robusto:** Usare un algoritmo di cifratura standard e robusto (AES-GCM) con una funzione di derivazione della chiave (KDF) come PBKDF2. |

### Categoria: Rischi Infrastrutturali

| Rischio | Probabilità | Impatto | Descrizione | Strategia di Mitigazione |
|---|---|---|---|---|
| **Perdita sessioni a riavvio Redis** | Media | Basso | Redis non ha la persistenza AOF abilitata per scelta consapevole (vedere `RUNBOOK.md` §4). Un riavvio del container Redis causa la perdita di tutte le sessioni attive. I dati applicativi (batch, mappings, chiavi di cifratura) sono su filesystem e non vengono persi. | 1. **Decisione documentata:** La volatilità è accettabile perché i dati critici sono su filesystem (`STATE_DIR`). 2. **Re-login trasparente:** Gli utenti vengono reindirizzati al login; nessun dato applicativo viene perso. 3. **Abilitare AOF** se il deployment richiede sessioni di lunga durata: aggiungere `--appendonly yes --appendfsync everysec` al comando Redis in `docker-compose.yml`. |
| **Perdita task Celery a riavvio Redis** | Bassa | Medio | Task Celery accodati ma non ancora avviati vengono persi se Redis si riavvia durante l'elaborazione. | ✅ **Parzialmente mitigato (v5.2.1):** 1. **Rollback automatico:** In caso di eccezione durante un task apply, Celery esegue rollback e il batch torna a stato `READY`. 2. **Idempotenza:** I task di scan/apply possono essere rilanciati senza effetti collaterali. 3. **Abilitare AOF** per garantire la durabilità della coda in ambienti critici. |

### Categoria: Rischi di Progetto e Adozione

| Rischio | Probabilità | Impatto | Descrizione | Strategia di Mitigazione |
|---|---|---|---|---|
| **Falsi Negativi** | Media | Alto | Il sistema potrebbe non rilevare tutte le occorrenze di dati sensibili, specialmente nomi propri o terminologia interna non presente nei dizionari. | ✅ **Parzialmente mitigato (v5.2.1):** 1. **MLNERDetector:** spaCy NER rileva nomi di persona/organizzazione non strutturati, riducendo i falsi negativi. 2. **LdapDetector:** arricchimento via directory aziendale per username e CN. 3. **Esecuzione parallela:** i detector ML e LDAP ora vengono sempre eseguiti senza rallentare il pipeline. 4. **Review Manuale:** il workflow pone la revisione umana come passaggio chiave obbligatorio. |
| **Complessità di installazione** | Media | Medio | L'utente target, sebbene tecnico, potrebbe avere difficoltà a installare Python, le dipendenze o a eseguire lo script di avvio, specialmente in ambienti Windows restrittivi. | ✅ **Mitigato:** Deployment Docker Compose con un solo comando (`docker compose up -d`); il README include una guida passo-passo. Il tool è completamente containerizzato — nessuna dipendenza locale richiesta. |
| **LDAP/ML server irraggiungibile** | Media | Medio | Se il server LDAP o il modello ML non sono disponibili, i detector correlati fallirebbero a cascata, bloccando l'intero pipeline. | ✅ **Mitigato (v5.2.1):** Circuit breaker (`app/core/circuit_breaker.py`) protegge entrambi i detector. Dopo 5 failure consecutive, il circuito si apre: il detector viene skippato silenziosamente per 60 secondi. Il pipeline continua con i detector regex/dizionario disponibili. |
