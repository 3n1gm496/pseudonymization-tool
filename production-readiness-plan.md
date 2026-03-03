# Piano di production readiness — v1.0

Questo documento traccia tutte le fasi e le PR necessarie per portare il progetto al 100% di production readiness. Ogni fase corrisponde a una PR specifica.

---

## FASE 1 — PR #33: Correzioni bloccanti

**Obiettivo:** Risolvere i problemi critici che impediscono qualsiasi deployment in produzione.

- **[ ] Punto 1.1 — `AUTH_SECRET` e `DEPLOYMENT_PROFILE` in docker-compose e .env.example**
  - Aggiungere `AUTH_SECRET` e `DEPLOYMENT_PROFILE=prod` come variabili obbligatorie nel `docker-compose.yml`.
  - Documentarle nel `.env.example` con valori di default sicuri e commenti chiari.
  - Aggiornare `validate_production_secrets()` per verificare anche `DEPLOYMENT_PROFILE`.

- **[ ] Punto 1.2 — Uvicorn multi-worker**
  - Modificare il CMD del Dockerfile in `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`.
  - Aggiungere una nota sul fatto che il rate limiter in-memory non è efficace con più worker.

- **[ ] Punto 1.3 — `allow_headers` CORS ristretto**
  - Sostituire `allow_headers=["*"]` con `allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "Accept"]` nel middleware CORS di `main.py`.

---

## FASE 2 — PR #34: Hardening errori e sicurezza

**Obiettivo:** Migliorare la gestione degli errori e la sicurezza dell'applicazione.

- **[ ] Punto 2.1 — Global exception handler**
  - Aggiungere un handler `@app.exception_handler(Exception)` in `main.py` che logga l'eccezione e restituisce una risposta 500 generica.

- **[ ] Punto 2.2 — Rimuovere `str(e)` dalle risposte HTTP**
  - In `console_routes.py`, `settings_routes.py` e `revert_routes.py`, loggare l'eccezione e restituire un messaggio generico.

---

## FASE 3 — PR #35: Infrastruttura TLS e reverse proxy

**Obiettivo:** Configurare un'infrastruttura di produzione sicura con TLS e reverse proxy.

- **[ ] Punto 3.1 — nginx.conf**
  - Creare `nginx/nginx.conf` con TLS termination, proxy_pass, header `X-Forwarded-For`, rate limiting e timeout.

- **[ ] Punto 3.2 — `docker-compose.prod.yml`**
  - Creare un override file che aggiunge il servizio nginx e gestisce i volumi per i certificati TLS.

- **[ ] Punto 3.3 — Healthcheck su `/api/ready`**
  - Modificare il HEALTHCHECK nel Dockerfile da `/api/health` a `/api/ready`.

---

## FASE 4 — PR #36: Rate limiting Redis-backed

**Obiettivo:** Implementare un rate limiter efficace in un ambiente multi-worker.

- **[ ] Punto 4.1 — Redis rate limiter**
  - Sostituire il rate limiter in-memory con uno basato su Redis.

---

## FASE 5 — PR #37: Coverage e qualità

**Obiettivo:** Aumentare la coverage dei test sui moduli critici.

- **[ ] Punto 5.1 — Test per `batches_routes.py` (48% → 70%)**
  - Aggiungere test per i path di errore Celery e la gestione di file corrotti.

- **[ ] Punto 5.2 — Test per `settings_routes.py` (48% → 75%)**
  - Aggiungere test per i path di errore del salvataggio stato.

---

## FASE 6 — PR #38: Monitoring e osservabilità

**Obiettivo:** Migliorare il monitoraggio e l'osservabilità dell'applicazione.

- **[ ] Punto 6.1 — Endpoint `/metrics` Prometheus**
  - Aggiungere `prometheus-fastapi-instrumentator` per esporre metriche HTTP.

- **[ ] Punto 6.2 — Log rotation**
  - Aggiungere configurazione del logging driver Docker in `docker-compose.yml`.

- **[ ] Punto 6.3 — Image tag versionato**
  - Modificare `image: pseudonymization-tool:latest` in `image: pseudonymization-tool:${APP_VERSION:-latest}` nel `docker-compose.yml`.
