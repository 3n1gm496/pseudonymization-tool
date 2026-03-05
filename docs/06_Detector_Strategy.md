# Strategia dei Detector

**Versione:** 5.2.1
**Data:** 2026-03-05

---

## 1. Filosofia di Rilevamento

La strategia di rilevamento si basa su un approccio **multi-livello, trasparente e configurabile**, privilegiando l'alta precisione e la chiarezza rispetto a un richiamo potenzialmente rumoroso. L'obiettivo è ridurre i falsi positivi, dando comunque all'utente il pieno controllo nella fase di review per correggere eventuali falsi negativi.

Il motore di rilevamento (`PseudonymizationEngine`) esegue tutti i detector **in parallelo** tramite `ThreadPoolExecutor` (max 4 worker). I risultati vengono aggregati e deduplicati prima di essere presentati all'utente. I detector lenti (LDAP, ML/NER) non bloccano l'esecuzione di quelli veloci (regex, dizionario).

---

## 2. Tipi di Detector

### 2.1. Detector Basati su Regex (Rule-Based)

Identificano entità che seguono un pattern strutturale definito. Veloci, con alta precisione.

| Entità | Confidenza di Default | Note |
|---|---|---|
| **Email** | 0.95 | Regex standard RFC 5322 semplificata. |
| **IPv4** | 1.00 | Validazione ottetti (0-255) inclusa. |
| **IPv6** | 0.90 | Pattern multi-forma; documentati i casi limite. |
| **URL** | 0.90 | `https?://` e `ftp://`; regex generica. |
| **Codice Fiscale** | 1.00 | Pattern rigido + checksum di controllo (algoritmo ministeriale). |
| **Partita IVA** | 0.85 | 11 cifre + validazione modulo 10. |
| **Numero Telefono** | 0.80 | Prefissi internazionali (`+39`), spazi, formati comuni. |

### 2.2. Detector Basati su Dizionario (Dictionary-Based)

Cercano corrispondenze esatte (case-insensitive) da liste di termini configurate dall'utente. Fondamentali per dati sensibili specifici del contesto organizzativo.

- **Directory:** `config/dictionaries/` (file di testo, un termine per riga)
- **Esempi:** `person_names.txt`, `internal_hostnames.txt`, `project_codes.txt`
- **Confidenza:** configurabile per dizionario, default 0.98.

### 2.3. Detector NER/ML (`MLNERDetector`)

Utilizza un modello spaCy (`it_core_news_sm` / `en_core_web_sm`) per il riconoscimento di entità contestuali: nomi di persona (`PER`), organizzazioni (`ORG`), luoghi (`LOC`). Compensano i falsi negativi dei detector basati su regole per entità non strutturate.

- **Confidenza:** variabile in base al punteggio spaCy, minimo 0.70.
- **Protezione:** circuit breaker (vedi §4).

### 2.4. Detector LDAP (`LdapDetector`)

Arricchisce il rilevamento interrogando la directory aziendale (LDAP/eDirectory/AD) per identificare nomi utente, CN, DN e attributi correlati presenti nel testo.

- **Distinto** da `ldap_auth.py` (autenticazione): `ldap_detector.py` è esclusivamente per l'arricchimento dei dati.
- **Protezione:** circuit breaker (vedi §4).

---

## 3. Gestione delle Sovrapposizioni (Overlaps)

Più detector possono identificare la stessa porzione di testo o porzioni sovrapposte.

**Strategia di risoluzione:**
1. **Specificità:** il finding con la stringa matchata più lunga vince.
2. **Confidenza:** a parità di lunghezza, vince il detector con confidenza più alta.
3. **Nessuna fusione:** viene scelto un singolo finding per ogni span; gli altri vengono scartati silenziosamente.

---

## 4. Resilienza: Circuit Breaker

I detector che dipendono da risorse esterne (LDAP server, modello ML) sono protetti da un `CircuitBreaker` generico (`app/core/circuit_breaker.py`).

| Parametro | Valore di Default |
|---|---|
| Soglia di apertura | 5 failure consecutive |
| Timeout riapertura | 60 secondi |
| Stato HALF-OPEN | 1 probe di test prima di chiudere |

**Comportamento:**
- **CLOSED:** detector attivo, tutte le chiamate vengono eseguite.
- **OPEN:** il detector viene skippato silenziosamente; il finding viene omesso (fail-safe). Lo stato è loggato a livello `WARNING`.
- **HALF-OPEN:** una singola chiamata di prova; se ha successo il circuito si richiude, altrimenti rimane aperto.

Il circuit breaker evita che un LDAP server irraggiungibile o un modello ML guasto causino timeout a cascata sull'intero pipeline.

---

## 5. Osservabilità

Ogni invocazione di detector produce metriche Prometheus:

- `detector_duration_seconds{detector="<nome>"}` — histogram della latenza.
- `file_processing_seconds{file_type="<tipo>"}` — histogram del tempo totale per tipo di file.

Le metriche sono visibili su `GET /api/metrics`.

Ogni operazione è correlata tramite `X-Request-ID`, propagato FastAPI → Celery → Worker per il tracing distribuito nei log strutturati.
