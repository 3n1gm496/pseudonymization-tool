> Questo file è stato aggiornato automaticamente da Manus per riflettere lo stato finale del progetto dopo 6 pull request.

# Changelog

Tutte le modifiche notevoli a questo progetto sono documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e questo progetto aderisce al [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
