# Rischi e Mitigazioni

**Autore:** Manus AI
**Versione:** 1.0 (MVP)
**Data:** 2026-02-25

---

## 1. Introduzione

Questo documento identifica i potenziali rischi tecnici, di progetto e di sicurezza che potrebbero impattare lo sviluppo e l'adozione del Local Pseudonymization Tool. Per ogni rischio, viene proposta una strategia di mitigazione per ridurne la probabilità o l'impatto.

## 2. Tabella dei Rischi

I rischi sono classificati per categoria e valutati in termini di probabilità e impatto (Altro, Medio, Basso).

### Categoria: Rischi Tecnici

| Rischio | Probabilità | Impatto | Descrizione | Strategia di Mitigazione |
|---|---|---|---|---|
| **Scarsa qualità dell'OCR** | Alta | Medio | L'OCR locale (Tesseract) potrebbe non riuscire a estrarre correttamente il testo da immagini di bassa qualità, screenshot complessi o con font non standard, portando a falsi negativi (dati sensibili non rilevati). | 1. **Trasparenza:** Informare chiaramente l'utente sui limiti dell'OCR. 2. **Warning Espliciti:** Se il motore OCR restituisce una confidenza bassa, marcare il file come "parzialmente processato" e inserire un warning prominente nel report. 3. **Guida Utente:** Fornire raccomandazioni su come produrre screenshot più "OCR-friendly". |
| **Complessità del parsing dei file** | Media | Alto | I formati come `.docx` e `.xlsx` sono complessi. La libreria di parsing potrebbe non gestire correttamente elementi specifici (es. commenti, note a piè di pagina, macro), lasciando dati sensibili non processati. | 1. **Scope Limitato:** Per l'MVP, dichiarare esplicitamente che verranno processati solo i contenuti testuali principali. 2. **Librerie Robuste:** Utilizzare librerie consolidate e ben mantenute (`python-docx`, `openpyxl`). 3. **Warning:** Segnalare nel report ogni elemento del documento che non è stato possibile analizzare. |
| **Performance Lente** | Media | Medio | L'elaborazione di batch di grandi dimensioni o di file molto grandi, specialmente se richiedono OCR, potrebbe risultare lenta e impattare negativamente l'esperienza utente. | 1. **Elaborazione Asincrona:** Il backend gestirà l'elaborazione in un thread separato per non bloccare l'interfaccia utente. 2. **Feedback Utente:** Fornire un feedback costante sullo stato di avanzamento. 3. **Ottimizzazione:** In fase di sviluppo, profilare il codice per identificare e ottimizzare i colli di bottiglia. |

### Categoria: Rischi di Sicurezza

| Rischio | Probabilità | Impatto | Descrizione | Strategia di Mitigazione |
|---|---|---|---|---|
| **Dati sensibili lasciati su disco** | Bassa | Alto | Bug nel processo di pulizia o un crash imprevisto potrebbero lasciare file originali o intermedi non cifrati nella directory temporanea. | 1. **Cleanup Robusto:** Implementare la logica di pulizia in un blocco `finally` per garantirne l'esecuzione anche in caso di eccezioni. 2. **Directory Dedicata:** Usare una directory temporanea specifica per ogni batch, rendendo più semplice la sua identificazione e rimozione. 3. **Raccomandazioni Operative:** Suggerire nel README l'uso del tool su macchine con crittografia del disco (es. BitLocker). |
| **Vulnerabilità in una dipendenza** | Media | Alto | Una delle librerie di terze parti utilizzate (es. FastAPI, `pypdf`) potrebbe avere una vulnerabilità di sicurezza non nota. | 1. **Minimizzare le Dipendenze:** Usare solo le librerie strettamente necessarie. 2. **Pinning delle Versioni:** Fissare le versioni delle dipendenze nel file `requirements.txt` a versioni note e stabili. 3. **Nessuna Esposizione di Rete:** Il binding del server solo su `127.0.0.1` riduce drasticamente la superficie di attacco, impedendo lo sfruttamento di eventuali vulnerabilità di rete da parte di attori esterni. |
| **Passphrase debole** | Alta | Medio | L'utente potrebbe scegliere una passphrase debole, rendendo il file di mapping vulnerabile ad attacchi di forza bruta offline. | 1. **Indicatore di Robustezza:** Implementare un semplice indicatore visivo della robustezza della passphrase nell'interfaccia utente. 2. **Raccomandazioni:** Mostrare un avviso che incoraggia l'uso di passphrase lunghe e complesse. 3. **Algoritmo Robusto:** Usare un algoritmo di cifratura standard e robusto (AES-GCM) con una funzione di derivazione della chiave (KDF) come PBKDF2. |

### Categoria: Rischi di Progetto e Adozione

| Rischio | Probabilità | Impatto | Descrizione | Strategia di Mitigazione |
|---|---|---|---|---|
| **Falsi Negativi** | Alta | Alto | Il sistema potrebbe non rilevare tutte le occorrenze di dati sensibili, specialmente nomi propri o terminologia interna non presente nei dizionari, creando un falso senso di sicurezza. | 1. **Review Manuale Obbligatoria:** L'architettura del workflow, che pone la review manuale come passaggio chiave, è la mitigazione principale. 2. **Trasparenza sui Limiti:** Comunicare chiaramente nel report e nella documentazione che i detector non sono infallibili e che la supervisione umana è fondamentale. 3. **Confidenza:** Mostrare i punteggi di confidenza per aiutare l'utente a focalizzare la review sui rilevamenti più incerti. |
| **Complessità di installazione** | Media | Medio | L'utente target, sebbene tecnico, potrebbe avere difficoltà a installare Python, le dipendenze o a eseguire lo script di avvio, specialmente in ambienti Windows restrittivi. | 1. **Script Semplici:** Creare script `.bat` e `.sh` il più possibile robusti e auto-contenuti. 2. **Documentazione Dettagliata:** Fornire una guida `README` con istruzioni passo-passo chiare, inclusi screenshot. 3. **Ambiente Virtuale:** Utilizzare `venv` per isolare le dipendenze ed evitare conflitti con altre installazioni Python sulla macchina dell'utente. |
