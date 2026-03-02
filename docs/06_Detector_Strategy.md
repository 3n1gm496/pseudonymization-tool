# Strategia dei Detector

**Autore:** Manus AI
**Versione:** 4.0.4
**Data:** 2026-03-02

---

## 1. Filosofia di Rilevamento

La strategia di rilevamento per l'MVP si basa su un approccio **multi-livello, trasparente e configurabile**, privilegiando l'alta precisione e la chiarezza rispetto a un richiamo potenzialmente rumoroso. L'obiettivo è ridurre i falsi positivi, dando comunque all'utente il pieno controllo nella fase di review per correggere eventuali falsi negativi.

Il motore di rilevamento funzionerà come una catena, dove ogni detector viene eseguito in sequenza sul testo estratto. I risultati di tutti i detector vengono aggregati prima di essere presentati all'utente.

## 2. Tipi di Detector (MVP)

Per l'MVP verranno implementate due categorie principali di detector.

### 2.1. Detector Basati su Regex (Rule-Based)

Questi detector utilizzano espressioni regolari per identificare entità che seguono un pattern strutturale ben definito. Sono veloci, efficienti e hanno un'alta precisione quando il pattern è robusto.

| Entità | Regex (Concettuale) | Confidenza di Default | Note |
|---|---|---|---|
| **Email** | `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` | 0.95 | Regex standard, molto affidabile. |
| **IPv4** | `\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b` | 1.00 | Verrà aggiunto un controllo per validare che ogni ottetto sia <= 255. |
| **IPv6** | Pattern complesso per le varie forme di IPv6. | 0.90 | La complessità della sintassi IPv6 può portare a falsi positivi/negativi. Sarà documentato. |
| **URL** | `https?://[\S]+` | 0.90 | Regex generica per catturare la maggior parte degli URL. |
| **Codice Fiscale** | Pattern specifico per la struttura del CF italiano. | 1.00 | La struttura è rigida e include un carattere di controllo, rendendo la regex molto precisa. |
| **Partita IVA** | `\b[0-9]{11}\b` | 0.85 | Un numero di 11 cifre potrebbe essere altro, ma nel contesto PA è probabile sia una P.IVA. La confidenza è leggermente più bassa. |
| **Numero Telefono** | Pattern che considera prefissi internazionali (es. `+39`), spazi e formati comuni. | 0.80 | Meno preciso a causa della varietà di formattazione. |

### 2.2. Detector Basati su Dizionario (Dictionary-Based)

Questi detector cercano corrispondenze esatte (case-insensitive) da liste di termini fornite dall'utente. Sono fondamentali per identificare dati sensibili specifici del contesto organizzativo.

- **Implementazione:** Il sistema leggerà i termini da file di testo semplici (un termine per riga) situati in una directory `config/dictionaries/`.
- **Struttura:**
    - `config/dictionaries/person_names.txt` (per nomi e cognomi comuni)
    - `config/dictionaries/internal_hostnames.txt` (per server interni)
    - `config/dictionaries/project_codes.txt` (per sigle di progetti)
    - etc.
- **Logica:** Per ogni parola nel testo, il sistema verificherà se appare in uno dei dizionari attivi. La ricerca sarà case-insensitive.
- **Confidenza:** La confidenza per i match da dizionario sarà configurabile, ma di default alta (es. 0.98), poiché si tratta di corrispondenze esplicite.

## 3. Gestione delle Sovrapposizioni (Overlaps)

Può accadere che più detector identifichino la stessa porzione di testo o porzioni sovrapposte. Esempio: `server-01.ente.gov.it` potrebbe essere matchato come `HOSTNAME` e come `URL` (se parte di un URL completo).

**Strategia di risoluzione (MVP):**
1.  **Priorità alla specificità:** Il finding più specifico (solitamente quello con la stringa matchata più lunga) vince. Nell'esempio sopra, l'URL completo avrebbe la priorità sull'hostname.
2.  **Confidenza:** A parità di specificità, vince il detector con la confidenza più alta.
3.  **Nessuna fusione:** Per l'MVP, non si tenterà di fondere i finding. Verrà scelto il 
