# Strict Repository Review — 2026-03-02

## Executive Summary

- Repo con buon volume di test backend, ma con BLOCKER architetturali: in produzione async Celery non può funzionare correttamente con stato batch solo in RAM.
- Frontend usa axios non configurato in quasi tutti i componenti: con CSRF attivo, i POST/PUT/DELETE sono destinati a fallire.
- Script di avvio dev/legacy sono rotti per path errati; “getting started” non è affidabile.
- Docker Compose espone credenziali di default e dipendenze inutili/insicure (RabbitMQ guest/guest) con dipendenze incrociate sbagliate.
- Docs recenti sono parzialmente “fantasy”: endpoint/status e comandi Celery non allineati al codice reale.
- CI valida solo backend Python; frontend build/lint/test non sono gate di qualità.
- Versioning incoerente in più punti (1.0.0 / 2.0.0-vNext / 4.0.4 / 4.1.0).
- Debito tecnico alto su duplicazione (audit/scrub) e catch broad exceptions.
- Stato attuale: NON firmerei produzione senza remediation immediata.
- Priorità: risolvere BLOCKER di architettura+CSRF+script, poi hardening e cleanup.

## Stato Generale del Repo

- Funzionalità core presenti, ma affidabilità prod bassa per mismatch tra design dichiarato e implementazione reale.
- Qualità test backend discreta; copertura frontend/integrazione distribuita quasi assente.
- Documentazione ampia ma non governata: molti documenti sono incoerenti tra loro.

## Top 5 Problemi Più Gravi

1. **Celery + stato in-memory = rottura prod**: worker e API non condividono `_batches` in RAM.
2. **CSRF frontend rotto**: componenti usano `axios` plain, ignorano interceptor token.
3. **Script startup broken**: `make dev` punta a script con path invalidi.
4. **Config write su volume read-only**: `/api/settings/state` scrive in `backend/config`, ma compose lo monta `:ro`.
5. **Sicurezza baseline debole**: password default hardcoded + secret runtime random non persistito.

## Lista Issue Prioritaria

| ID | Severità | Categoria | Dove | Sintomo / rischio | Fix raccomandato | Effort |
|---|---|---|---|---|---|---|
| I-001 | BLOCKER | Bug | `backend/app/core/batch_manager.py`, `backend/app/core/tasks.py`, `docker-compose.yml` | Worker Celery non vede batch creati dall’API (RAM separata) | Persisti batch/decision/passphrase in storage condiviso (DB/Redis) e fai lookup dal worker | L |
| I-002 | BLOCKER | Security | `frontend/src/components/Scanner.jsx`, `frontend/src/components/FindingsTable.jsx`, `frontend/src/utils/axios.js`, `backend/app/main.py` | CSRF header non inviato dai componenti principali | Sostituisci tutti gli import `axios` con client centralizzato in `utils/axios.js` | M |
| I-003 | BLOCKER | Build | `scripts/dev-stack.sh`, `Makefile` | `make dev` non trova backend/frontend directory | Correggi path a `../backend` e `../frontend` (o calcola root repo robustamente) | S |
| I-004 | HIGH | Build | `scripts/legacy/start.sh`, `scripts/legacy/prepare_offline.sh` | Script legacy inutilizzabili fuori documentazione | Correggi path relativi (`../../backend` o root resolver) + test smoke script | S |
| I-005 | HIGH | Bug | `backend/app/api/settings_routes.py`, `docker-compose.yml` | `/settings/state` fallisce in Docker (FS read-only) | Scrivi stato in volume RW dedicato (`/tmp` o `/app/data`) | S |
| I-006 | HIGH | Security | `docker-compose.yml`, `backend/app/core/auth.py` | Credenziali default + secret non persistito, sessioni invalidate al restart | Rimuovi default password, rendi `AUTH_SECRET` mandatory in prod, fail-fast all’avvio | M |
| I-007 | HIGH | Performance | `frontend/src/components/Scanner.jsx`, `backend/app/api/batches_routes.py` | Polling ogni 1.5s su endpoint che restituisce tutti i findings | Aggiungi endpoint lightweight `/batches/{id}/status` (status/progress/error) | M |
| I-008 | HIGH | Docs | `README.md`, `backend/app/api/batches_routes.py` | README dichiara endpoint `/status` inesistente | O implementi endpoint, o correggi docs subito | S |
| I-009 | HIGH | Docs/Build | `docs/11_Deployment_Guide.md`, `backend/app/core/tasks.py` | Docs usano `app.core.task` ma modulo reale è `app.core.tasks` | Correggi tutti i comandi Celery/Flower in docs | S |
| I-010 | MEDIUM | Build/Security | `docker-compose.yml` | RabbitMQ guest/guest avviato e richiesto, ma broker Celery è Redis | Rimuovi RabbitMQ dal default profile o rendilo opzionale via profile dedicato | S |
| I-011 | MEDIUM | CI | `.github/workflows/ci.yml` | Nessun gate frontend (build/lint/test) | Aggiungi job Node: install + lint + build | S |
| I-012 | MEDIUM | Cleanup | `backend/app/core/scan_queue.py` | Codice async queue legacy non usato | Depreca/rimuovi o reintegra con scelta architetturale unica | S |
| I-013 | MEDIUM | DX | `backend/app/api/auth_routes.py`, `backend/app/main.py`, `backend/app/core/logging_config.py` | Versioning incoerente | Introduci singola sorgente versione (`app/__init__.py`) | S |
| I-014 | MEDIUM | Code Quality | `backend/app/api/batches_routes.py`, `backend/app/api/settings_routes.py`, `backend/app/api/revert_routes.py`, `backend/app/api/console_routes.py`, `backend/app/api/auth_routes.py` | Duplica `_scrub_sensitive` in 5 file | Estrai modulo comune `app/core/audit.py` | S |
| I-015 | MEDIUM | Tests | `backend/tests/conftest.py` | Fixture autouse disabilita auth/CSRF quasi ovunque | Riduci scope fixture, crea test matrix auth-on/auth-off | M |

## Pulizia Senza Pietà

### Dead Weight Probabile

- `backend/app/core/scan_queue.py`: coda legacy non usata (Celery già introdotto).
- `code_review_report.md`: documento enorme operativo non necessario al runtime.
- `test_results_summary.txt`: output snapshot, non source-of-truth.
- `docs/18_CODE_REVIEW_FINDINGS.md` + documenti “audit” multipli: rischio divergenza con docs principali.

### Dipendenze Inutilizzate o Sospette

- `rabbitmq` service in compose non usato da broker Celery.
- `hypothesis`, `faker`, `pylint`, `mypy` in `backend/requirements-dev.txt` non eseguiti in CI.
- `flower` in runtime deps: meglio opzionale (extra/dev profile).

### Script/CI Steps Ridondanti

- Doppio flake8, secondo con `--exit-zero` ha valore basso.
- 4 run separati pytest coverage regression: costoso e rumoroso.

### Config Duplicate

- Versione app hardcoded in più posti.
- Parametri test sia in `pyproject.toml` sia forzati in CI.

## Coerenza Docs

### Dove README/docs mentono o sono incomplete

- Endpoint status dichiarato ma non implementato (`README.md` vs router reale).
- Deployment guide usa modulo sbagliato (`app.core.task` vs `app.core.tasks`).
- Frontend README indica `index.css` ma codice usa `index.pcss`.

### Sezioni da riscrivere (bozza)

**README (async flow):**

> POST /api/batches restituisce 202 con task_id. Lo stato si legge con GET /api/batches/{id} (oppure /status se abilitato). Frontend usa polling lightweight, non full findings.

**Deployment guide (Celery command):**

> Comando worker: `celery -A app.core.tasks worker ...`

**Settings persistence:**

> Settings state path deve essere volume RW dedicato, non `backend/config` read-only.

### Getting started verificato

- `make dev`: non affidabile finché non si correggono i path in `scripts/dev-stack.sh`.
- `make legacy-start` / offline scripts: non affidabili finché non si correggono i path backend.

## Qualità del Codice

### Refactor ad alto ROI (5-10)

1. Unifica audit/scrub in modulo unico.
2. Sostituisci dict globali batch con repository layer (Redis/DB).
3. Introduci DTO per status polling (no findings pesanti).
4. Centralizza versione app.
5. Elimina stringhe “FIX #xx” dal codice runtime; spostale in changelog.
6. Crea dependency injection config (evita env sparsi).
7. Riduci `except Exception` nei path critici con errori tipizzati.
8. Separa API sync/async in router distinti o naming esplicito.
9. Aggiungi schema per settings state e validazione strict.
10. Rimuovi/archivia `scan_queue.py`.

### Error handling: cosa manca e dove

- Task distributed failure mode (batch not found) non mitigato strutturalmente.
- `settings/state` fa catch broad e torna 500 senza remediation hint.

### Logging/observability: cosa manca e dove

- Mancano metriche su queue lag, task latency percentile, fail/retry rate.
- Nessun correlation-id consistente API→task→download.

## Test Plan

### Coverage mancante

- Integrazione reale API container + worker container + Redis (non eager mode).
- Frontend CSRF end-to-end.
- Settings persistence con mount read-only.
- Startup scripts smoke.

### 5 test da aggiungere subito

1. `backend/tests/test_distributed_celery_integration.py`: batch creato API, worker separato processa davvero.
2. `backend/tests/test_settings_state_rw.py`: verifica scrittura state path in docker profile.
3. `frontend/src/__tests__/csrf_client.test.jsx`: assicura uso client axios centralizzato.
4. `backend/tests/test_batch_status_payload_size.py`: `/batches/{id}` non usato per polling massivo.
5. `scripts/tests/test_startup_paths.sh`: verifica path script dev/legacy.

### Test flaky o troppo lenti

- Live E2E con `RUN_LIVE_E2E=1` non sono gate reali e rischiano drift.

## Sicurezza

### Checklist rapida

- Segreti: ❌ default password hardcoded; secret non obbligatorio.
- Injection: ⚠️ base buona su filename sanitization, ma broad exceptions nascondono failure mode.
- Dependency risk: ⚠️ `safety` non bloccante in CI (`|| true`).
- Permessi: ❌ settings tenta write su path ro.
- Input validation: ⚠️ discreta, ma coverage non prova flussi browser reali con CSRF.

### Azioni immediate

- Blocca avvio se `AUTH_PASSWORD` default o se `AUTH_SECRET` mancante in prod.
- Fix path script dev/legacy.
- Migra frontend a axios centralizzato.
- Correggi docs comandi Celery.

### Azioni medio termine

- Stato batch persistente condiviso.
- Endpoint status lightweight.
- CI frontend completa.
- Riduzione broad exception + logging strutturato end-to-end.

## PR Plan

### PR1: Quick wins (LOW risk)

- Scope: script path fix, docs command fix, versioning single source, remove dead imports.
- File: `scripts/dev-stack.sh`, `scripts/legacy/start.sh`, `scripts/legacy/prepare_offline.sh`, `README.md`, `docs/11_Deployment_Guide.md`, `backend/app/core/logging_config.py`, `backend/app/main.py`.

### PR2: Bugfix critici (MEDIUM risk)

- Scope: frontend usa client axios centralizzato, CSRF end-to-end, settings path RW.
- File: componenti frontend con axios plain, `backend/app/api/settings_routes.py`, `docker-compose.yml`.

### PR3: Refactor strutturale (HIGH risk)

- Scope: persistenza batch condivisa (Redis/DB), worker/API coherence, endpoint status lightweight.
- File: `backend/app/core/batch_manager.py`, `backend/app/core/tasks.py`, `backend/app/api/batches_routes.py`, nuovi moduli repository/storage.

### PR4: Docs + CI (LOW-MEDIUM risk)

- Scope: allineamento docs a comportamento reale, aggiunta frontend job CI, test integration distributed.
- File: `.github/workflows/ci.yml`, docs tecniche e test plan.

---

**Nota operativa:** questo file è stato generato da review severa con ancoraggio su codice/config/script reali al 2026-03-02, ed è pensato come baseline di remediation.
