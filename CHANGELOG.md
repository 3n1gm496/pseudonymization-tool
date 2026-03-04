> Questo file è stato aggiornato automaticamente da Manus per riflettere lo stato finale del progetto dopo 6 pull request.

# Changelog

Tutte le modifiche notevoli a questo progetto sono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e questo progetto aderisce al [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

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
