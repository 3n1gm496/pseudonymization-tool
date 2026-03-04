> Questo file è stato aggiornato automaticamente da Manus per riflettere lo stato finale del progetto dopo 6 pull request.

# Changelog

Tutte le modifiche notevoli a questo progetto sono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e questo progetto aderisce al [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [5.2.0] - 2026-03-04

### Added

- **Autenticazione Ibrida (LDAP + Locale) (PR #61)**
  - Aggiunta la possibilità di autenticarsi tramite un server LDAP (eDirectory, Active Directory) come alternativa al database locale.
  - Nella pagina di login, l'utente può scegliere esplicitamente il metodo di autenticazione.
  - I ruoli (`admin`, `operator`) vengono mappati dinamicamente in base all'appartenenza dell'utente a specifici gruppi LDAP.
  - In caso di irraggiungibilità del server LDAP, il sistema garantisce il login per gli utenti locali (fallback).

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

## [5.1.0] - 2026-03-03

### Added

- **Notifiche SSE per batch asincroni (PR #59)**
  - Aggiunto endpoint `GET /api/batches/{id}/events` in `batches_routes.py` che emette eventi Server-Sent Events (`text/event-stream`) con aggiornamenti di stato in tempo reale.
  - Il frontend (`Scanner.tsx`, `App.tsx`) si connette via `EventSource` e riceve aggiornamenti push senza polling. In caso di disconnessione, il fallback automatico al polling garantisce la continuità operativa.
  - Aggiunto `backend/tests/test_sse_events.py` con **10 test** (7 asincroni + 3 HTTP) che coprono: evento `connected`, terminazione su `done`/`done_with_errors`/`error`, batch non trovato, deduplicazione eventi, transizioni di stato, Content-Type e Cache-Control.

- **Sistema multi-utente con ruoli admin/operator (PR #58)**
  - Aggiunto `app/core/user_manager.py`: gestione utenti locali con SQLite, hash bcrypt, bootstrap automatico al primo avvio con password generata casualmente.
  - Aggiunto `app/api/users_routes.py`: endpoint REST per CRUD utenti (`GET/POST /api/users`, `GET /api/users/me`, `GET/PUT/DELETE /api/users/{username}`).
  - Modificato `app/core/auth.py`: `verify_credentials` ora interroga `user_manager` (SQLite) con fallback legacy su `AUTH_PASSWORD`; `validate_session` ritorna `(username, role)` invece di solo `username`.
  - Aggiunto `frontend/src/components/UserManagement.tsx`: pannello gestione utenti (solo admin).
  - Aggiornato `frontend/src/components/SettingsPanel.tsx`: tab "Utenti" visibile solo agli admin.
  - Aggiornato `frontend/src/components/Header.tsx`: badge del ruolo utente corrente.
  - Aggiunto `backend/tests/test_user_manager.py` (51 test) e `backend/tests/test_users_routes.py` (31 test).
  - Aggiunto `bcrypt` a `requirements.txt`; rimosso `passlib`.

- **Coverage exceptions.py 100% (PR #56)**
  - Aggiunto `tests/test_exceptions.py` con **62 test case** che coprono tutte le 35 classi di eccezione del dominio e le due funzioni helper (`exception_to_http_status`, `exception_to_detail`).
  - La coverage di `app/core/exceptions.py` passa dal **60% al 100%**.

### Changed

- **Documentazione Redis AOF (PR #54)**
  - Aggiunta sezione dedicata nel `RUNBOOK.md` (§4) che documenta la decisione architetturale consapevole di non abilitare la persistenza AOF di default, con istruzioni per abilitarla in ambienti con requisiti di durabilità elevati.
  - Aggiornato `docs/08_Risks_and_Mitigations.md` con due nuovi rischi documentati: perdita sessioni e perdita task Celery a riavvio Redis.
  - Aggiunto commento esplicativo in `docker-compose.yml` sulla configurazione Redis.

- **Refactoring batch_manager.py (PR #55)**
  - Estratto il layer Redis in `app/core/batch_redis.py` (client caching, chiavi, serializzazione Redis).
  - Estratto il layer filesystem in `app/core/batch_persistence.py` (path management, atomic write, cifratura disco).
  - `batch_manager.py` ora contiene solo la logica di business e ri-espone l'API pubblica invariata (zero breaking changes).

### Fixed

- **Diagramma Mermaid README (PR #57)**
  - Sostituiti i `\n` letterali con `<br/>` nei label dei 6 nodi del diagramma architetturale. GitHub Mermaid 10.x non interpreta `\n` come newline — i caratteri venivano mostrati come testo letterale.

---

## [5.1.0] - 2026-03-03

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
