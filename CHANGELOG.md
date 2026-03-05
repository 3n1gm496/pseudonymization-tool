# Changelog

Tutte le modifiche notevoli a questo progetto sono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e questo progetto aderisce al [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [5.2.1] - 2026-03-05

### Added

- **Distributed Trace Correlation via X-Request-ID**
  - Aggiunto middleware FastAPI che genera o propaga l'header `X-Request-ID` su ogni request.
  - Il `task_id` di Celery viene impostato al valore dell'`X-Request-ID` ricevuto, garantendo la correlazione end-to-end FastAPI → Celery → Worker.
  - Tutti i log strutturati includono il campo `request_id` per il tracing distribuito.

- **Prometheus Histograms per Detector e File-Type**
  - Aggiunto `detector_duration_seconds` (histogram) per misurare la latenza di ogni detector.
  - Aggiunto `file_processing_seconds` (histogram) per misurare il tempo di elaborazione per tipo di file.
  - Le metriche sono esposte sull'endpoint `/api/metrics` in formato Prometheus.

- **Circuit Breaker per LDAP e ML Detector**
  - Implementato `CircuitBreaker` generico in `app/core/circuit_breaker.py`.
  - `LdapDetector` e `MLNERDetector` sono ora protetti da circuit breaker con soglie configurabili: 5 failure consecutive aprono il circuito per 60 secondi.
  - Lo stato del circuit breaker (CLOSED/OPEN/HALF-OPEN) è visibile nei log strutturati.

- **Esecuzione Parallela dei Detector**
  - I detector nel `PseudonymizationEngine` ora vengono eseguiti in parallelo tramite `ThreadPoolExecutor` con `max_workers=4`.
  - I detector lenti (LDAP, ML) non bloccano più l'esecuzione dei detector veloci (regex, dizionario).
  - Riduzione attesa stimata del 40-60% su testi che attivano detector multipli.

- **Endpoint `POST /api/auth/test-auth`**
  - Nuovo endpoint per testare la connettività LDAP senza eseguire un login completo.
  - Utile per diagnosticare problemi di configurazione LDAP in fase di setup.

### Changed

- **LDAP DN Regex Hardening**
  - Il parser dei DN LDAP ora rigetta DN con componenti vuoti (es. `cn=,dc=example`).
  - Aggiunto cap a 64 componenti massimi per prevenire ReDoS su input malformati.

- **Redazione Campi Sensibili LDAP nell'API**
  - I campi `auth_admin_group_dn` e `auth_operator_group_dn` vengono redatti (sostituiti con `***`) nelle risposte GET delle impostazioni, per evitare l'esposizione di struttura LDAP interna.

### Fixed

- **5 Bug nel Pipeline di Pseudonimizzazione**
  - `batch_manager.py`: corretta la race condition nel cleanup che poteva eliminare batch ancora attivi.
  - `tasks.py`: aggiunto rollback Celery in caso di eccezione durante l'apply, evitando stato inconsistente.
  - `batches_routes.py`: UUID filter in `list_batches` per ignorare entry non-UUID nella directory di stato.
  - `revert_routes.py`: `ValueError` da `get_batch_dir` ora catturato correttamente in tutti i loader su disco.
  - `batch_manager.py`: rimossa la guardia ridondante `ValueError` da `get_batch_dir` (la validazione avviene a monte).

- **Pulizia Passphrase in Memoria**
  - La passphrase viene azzerata dalla memoria (`\x00 * len`) immediatamente dopo l'uso nel processo di cifratura del mapping.

- **Validazione Campi LDAP Auth**
  - `auth_user_base_dn`, `auth_admin_group_dn`, `auth_operator_group_dn` sono ora validati come DN non-vuoti prima del salvataggio in `settings_routes.py`.

- **Correttezza Checksum Codice Fiscale**
  - Il validatore del CF ora calcola correttamente il carattere di controllo per tutti i casi limite.

- **CI/CD**
  - Aggiunta configurazione `flake8` strict in `setup.cfg` (E501 con line-length=120, W503 ignorato).
  - Soglia di copertura per `ldap_auth.py` corretta in `pyproject.toml` al valore misurato reale.
  - Riformattazione `black` su tutti i file modificati.
  - Corretto `# nosec` annotation su `B108` (uso di `/tmp` intenzionale e documentato).

---

## [5.2.0] - 2026-03-04

### Added

- **Autenticazione Ibrida (LDAP + Locale) (PR #61)**
  - Creato `app/core/ldap_auth.py`: modulo dedicato all'autenticazione tramite LDAP, distinto da `ldap_detector.py` (arricchimento dati). Supporta eDirectory (NetIQ/Novell) e Active Directory tramite la libreria `ldap3`.
  - L'autenticazione si basa sull'attributo `cn` dell'objectClass `inetOrgPerson`, come richiesto per eDirectory.
  - Aggiunto endpoint `GET /api/auth/ldap-status`: ritorna se l'autenticazione LDAP è abilitata, usato dal frontend per mostrare/nascondere l'opzione.
  - Aggiornato `POST /api/auth/login`: accetta il campo `auth_method` (`local` o `ldap`) per la scelta esplicita del metodo da parte dell'utente (Opzione C).
  - Aggiornato `app/core/auth.py`: `verify_credentials` ora gestisce due rami separati (`ldap` e `local`). In caso di fallimento LDAP, non si fa fallback al login locale (Opzione X, fail-safe).
  - Aggiornato `frontend/src/components/LoginForm.tsx`: aggiunta UI per la scelta del metodo di autenticazione (bottoni "Locale" / "Aziendale (LDAP)"), visibile solo se LDAP è configurato.
  - Aggiornato `frontend/src/App.tsx`: `handleLogin` propaga il parametro `auth_method` all'endpoint backend.
  - Esteso `LdapConfig` in `schemas.py` con i campi: `auth_enabled`, `auth_user_base_dn`, `auth_admin_group_dn`, `auth_operator_group_dn`, `auth_default_role`.
  - Aggiunta `ldap3>=2.9.1` a `requirements.txt`.
  - Aggiunto `backend/tests/test_ldap_auth.py` con **39 test** che coprono: flusso completo, password errata, utente non trovato, server non raggiungibile, mapping ruoli, appartenenza gruppi, bind di servizio.

### Changed

- **Versione e Test Badge Aggiornati (PR #60)**
  - Versione del progetto aggiornata a `v5.2.0`.
  - Badge dei test nel `README.md` aggiornato per riflettere il numero corretto di test (774).

- **Documentazione Architetturale (PR #60)**
  - Aggiunte al file `02_Technical_Architecture.md` tre nuove sezioni:
    - `2.5. Multi-User Authentication`: descrive l'architettura del sistema di autenticazione locale con SQLite e bcrypt.
    - `2.6. Real-time Notifications (SSE)`: illustra il funzionamento delle notifiche push per gli aggiornamenti di stato dei batch.
    - `2.7. Contextual Data Enrichment (LDAP)`: chiarisce l'uso di LDAP come fonte dati per migliorare il rilevamento delle entità, distinguendolo dall'autenticazione.

### Fixed

- **Correzioni CI e Test Post-Migrazione TypeScript (PR #53)**
  - Corretta la configurazione di ESLint per gestire correttamente i file TypeScript.
  - Aggiornati i test Python che interagivano con il frontend per allinearli alla nuova struttura del codice TypeScript.

## [5.1.1] - 2026-03-04

### Added

- **Migrazione Completa a TypeScript (PR #52)**
  - Tutti i file sorgente del frontend (componenti React, utility) sono stati migrati da JavaScript a TypeScript (`.tsx`, `.ts`).
  - Abilitato lo `strict mode` di TypeScript per garantire massima type safety.

- **Audit Log Persistente (PR #51)**
  - Introdotto un sistema di audit log che traccia tutte le azioni critiche (login, scan, apply, download) su un database SQLite (`audit.db`).
  - Aggiunta una nuova interfaccia utente in sola lettura per permettere agli amministratori di consultare e filtrare i log di audit.

- **Aumento Copertura Test Autenticazione (PR #50)**
  - Aumentata la copertura dei test per il sistema di autenticazione, con un focus specifico sui percorsi che coinvolgono Redis e la gestione delle sessioni in scenari di edge case.

### Changed

- **Formattazione Codice (PR #49)**
  - Applicata la formattazione automatica con `black` al file `tasks.py` per allinearlo agli standard del progetto.

### Fixed

- **Correzione Dipendenze Frontend (PR #48)**
  - Sostituito `pnpm-lock.yaml` con `package-lock.json` per risolvere problemi di inconsistenza delle dipendenze nell'ambiente di CI.

### Fixed

- **Diagramma Mermaid README (PR #57)**
  - Sostituiti i `\n` letterali con `<br/>` nei label dei 6 nodi del diagramma architetturale. GitHub Mermaid 10.x non interpreta `\n` come newline — i caratteri venivano mostrati come testo letterale.

---

## [5.0.0] - 2026-03-03

Questa versione segna il completamento del piano di **production readiness**, rendendo il tool robusto, sicuro e pronto per il deployment in ambienti enterprise.

### Added

- **Infrastruttura di Produzione (PR #35)**
  - Aggiunto un reverse proxy **nginx** con terminazione TLS, security header, e rate limiting a livello IP.
  - Creato un file `docker-compose.prod.yml` per orchestrare il deployment di produzione.

- **Monitoring e Osservabilità (PR #38)**
  - Aggiunto un endpoint `/api/metrics` in formato **Prometheus** per il monitoring applicativo.
  - Le metriche includono contatori per scan/apply, errori HTTP, e un gauge per i batch attivi.

- **Test Coverage (PR #37)**
  - Aggiunti **37 nuovi test** per `settings_routes.py` e `console_routes.py`, aumentando la **copertura totale dal 71% all'82%**.

### Changed

- **Gestione Errori (PR #34)**
  - Implementato un **global exception handler** per prevenire l'esposizione di dettagli di errori interni (information leakage).

- **Configurazione (PR #33)**
  - Il numero di worker Uvicorn è ora configurabile tramite la variabile d'ambiente `WEB_CONCURRENCY`.
  - La configurazione CORS è ora dinamica in base al `DEPLOYMENT_PROFILE`.

- **Deployment (PR #38)**
  - L'immagine Docker nel `docker-compose.yml` è ora versionata (`pseudonymization-tool:5.0.0`) per garantire deployment riproducibili.

### Fixed

- **Sicurezza Critica (PR #33)**
  - Le variabili d'ambiente critiche (`AUTH_SECRET`, `DEPLOYMENT_PROFILE`) sono ora obbligatorie e documentate.

- **Rate Limiting (PR #36)**
  - Il rate limiter è stato migrato da in-memory a **Redis-backed** (sliding window log), rendendolo efficace in ambienti multi-worker.

- **Healthcheck (PR #35)**
  - L'healthcheck Docker ora usa l'endpoint `/api/ready` per una verifica più affidabile dello stato del servizio.

---

## [5.0.0] - ... (versioni precedenti)
