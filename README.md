> Questo file è stato aggiornato automaticamente da Manus per riflettere lo stato finale del progetto dopo 6 pull request.

# Local Pseudonymization Tool v5.0.0

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/) [![React 18.2](https://img.shields.io/badge/React-18.2-61dafb.svg)](https://react.dev) [![FastAPI 0.110](https://img.shields.io/badge/FastAPI-0.110-009688.svg)](https://fastapi.tiangolo.com) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 483 passing](https://img.shields.io/badge/Tests-483%20passing-brightgreen.svg)](backend/tests/) [![Coverage: 82%](https://img.shields.io/badge/Coverage-82%25-brightgreen.svg)](https://github.com/3n1gm496/pseudonymization-tool/pull/37) [![Monitoring: Prometheus](https://img.shields.io/badge/Monitoring-Prometheus-orange.svg)](#-monitoring-prometheus)

Web application locale moderna per la pseudonimizzazione sicura di dati sensibili in documenti di testo, DOCX, XLSX, PDF e immagini. Interfaccia React con Tailwind CSS, darkmode supportato. Progettato per ambienti enterprise che richiedono massima sicurezza e capacità di operare completamente offline.

🔗 **Repository:** [github.com/3n1gm496/pseudonymization-tool](https://github.com/3n1gm496/pseudonymization-tool)

## ✨ Caratteristiche Principali

| Categoria | Funzionalità |
|---|---|
| **Core** | **100% Offline** (nessuna chiamata esterna), **Multi-formato** (TXT, DOCX, XLSX, PDF, immagini), **Deterministico** (stesso input = stesso output) |
| **Sicurezza** | **Mapping cifrato AES-256-GCM**, **Global exception handling** (no information leakage), **HTTP security headers** (via nginx), **CSRF protection** |
| **Architettura** | **Architettura Asincrona** (Celery + Redis), **Multi-worker support** (Uvicorn), **TLS/HTTPS** (via nginx reverse proxy), **Rate Limiting** (Redis-backed) |
| **Funzionalità** | **Modalità Flessibili** (`light`/`strict`), **Preset Policy** (`SOC Logs`), **Review Manuale**, **Report Dettagliati** (HTML/JSON) |
| **Operatività** | **Docker Compose ready** (`dev` e `prod`), **Readiness/Liveness API** (`/api/ready`, `/api/health`), **Monitoring con Prometheus** (`/api/metrics`) |

---

## 📋 Indice

- [Architettura](#-architettura)
- [Quick Start (Docker)](#-quick-start-docker)
- [Deployment in Produzione](#-deployment-in-produzione)
- [Monitoring (Prometheus)](#-monitoring-prometheus)
- [Configurazione](#-configurazione)
- [Sicurezza](#-sicurezza)
- [Sviluppo](#-sviluppo)

---

## 🏗️ Architettura

Il sistema è progettato per essere modulare, scalabile e sicuro, separando il frontend, il backend e i task asincroni in container Docker distinti.

```mermaid
graph TD
    subgraph "User Browser"
        Frontend[💻 Frontend<br>(React, Tailwind CSS)]
    end

    subgraph "Infrastruttura Server"
        Nginx[🌐 nginx Reverse Proxy<br>TLS Termination, Rate Limiting, Security Headers]
        Backend[🚀 Backend API<br>(FastAPI, Uvicorn)]
        Worker[⚙️ Celery Worker<br>(Task asincroni)]
        Redis[💾 Redis<br>(Broker, Cache, Rate Limiter)]
        Prometheus[📊 Prometheus<br>(Scrape /api/metrics)]
    end

    Frontend -- HTTPS --> Nginx
    Nginx -- HTTP --> Backend
    Backend -- Task --> Redis
    Worker -- Task --> Redis
    Backend -- Legge/Scrive --> Redis
    Prometheus -- Scrape --> Nginx
```

- **nginx**: funge da reverse proxy, gestendo la terminazione TLS, il rate limiting a livello IP e l'aggiunta di security header (HSTS, X-Frame-Options, etc.).
- **Backend (FastAPI)**: espone le API REST, gestisce l'autenticazione, la logica di business e l'invio di task a Celery.
- **Celery Worker**: esegue in background i task di lunga durata (scansione e pseudonimizzazione dei file) senza bloccare l'API.
- **Redis**: serve come message broker per Celery, cache per le sessioni utente e backend per il rate limiting distribuito.

---

## ⚡ Quick Start (Docker)

**Prerequisiti**: Docker e Docker Compose installati.

1.  **Clonare il repository:**
    ```bash
    git clone https://github.com/3n1gm496/pseudonymization-tool.git
    cd pseudonymization-tool
    ```

2.  **Creare e configurare `.env`:**
    Copia il file di esempio e genera le chiavi segrete necessarie.
    ```bash
    cp .env.example .env
    
    # Popola .env con valori sicuri (le password sono obbligatorie)
    echo "AUTH_PASSWORD=$(openssl rand -base64 24)" >> .env
    echo "REDIS_PASSWORD=$(openssl rand -base64 24)" >> .env
    echo "AUTH_SECRET=$(openssl rand -base64 48)" >> .env
    echo "FLOWER_USER=admin" >> .env
    echo "FLOWER_PASSWORD=$(openssl rand -base64 24)" >> .env
    ```

3.  **Avviare i servizi:**
    Il `Makefile` astrae i comandi Docker Compose per semplicità.
    ```bash
    make start
    ```

L'applicazione sarà disponibile su **http://localhost:8000**.

**Comandi utili:**
- `make logs`: Visualizza i log di tutti i container.
- `make stop`: Ferma e rimuove i container.
- `make health`: Controlla lo stato degli endpoint `health` e `ready`.
- `make monitoring`: Avvia i servizi con il profilo `monitoring` (include Flower UI su http://localhost:5555).

---

## 🚀 Deployment in Produzione

Per un ambiente di produzione, è fornito un file `docker-compose.prod.yml` che orchestra il backend insieme a un reverse proxy **nginx**.

**Funzionalità aggiuntive del setup di produzione:**
- **Terminazione TLS/HTTPS**: nginx gestisce i certificati SSL.
- **Security Header**: Aggiunta automatica di header come `Strict-Transport-Security` e `X-Content-Type-Options`.
- **Rate Limiting a livello IP**: Protezione contro attacchi di forza bruta o DoS.
- **Certificati Self-Signed**: Script per generare certificati di sviluppo inclusi.

### Avvio in Produzione

1.  **Configura `.env`**: Assicurati che `DEPLOYMENT_PROFILE` sia impostato su `prod` e che `PROD_FRONTEND_URL` corrisponda al dominio pubblico (es. `https://pseudonymizer.example.com`).

2.  **Genera i certificati**: Per lo sviluppo, puoi usare lo script fornito.
    ```bash
    ./scripts/generate-dev-certs.sh
    ```
    In produzione, sostituisci `nginx/certs/dev.crt` e `nginx/certs/dev.key` con i tuoi certificati firmati da una CA.

3.  **Avvia con il file di produzione:**
    ```bash
    docker compose -f docker-compose.prod.yml up --build -d
    ```

L'applicazione sarà esposta sulla porta **443 (HTTPS)**.

---

## 📊 Monitoring (Prometheus)

L'applicazione espone un endpoint `/api/metrics` in formato Prometheus per il monitoring.

**Metriche principali:**
| Metrica | Tipo | Descrizione |
|---|---|---|
| `pseudonymizer_scans_total` | Counter | Numero di scansioni completate (con label `preset`) |
| `pseudonymizer_applies_total` | Counter | Numero di apply completati |
| `pseudonymizer_errors_total` | Counter | Errori HTTP (con label `status_code`, `endpoint`) |
| `pseudonymizer_active_batches` | Gauge | Numero di batch attivi in memoria |
| `pseudonymizer_http_requests_total` | Counter | Richieste HTTP totali (con label `method`, `endpoint`, `status`) |

L'endpoint è esentato da autenticazione e CSRF per facilitare lo scraping. In produzione, l'accesso a `/api/metrics` dovrebbe essere limitato a livello di rete (es. consentito solo dall'IP del server Prometheus).

---

## ⚙️ Configurazione

La configurazione avviene tramite **variabili d'ambiente**, definite nel file `.env`.

| Variabile | Descrizione | Default |
|---|---|---|
| `DEPLOYMENT_PROFILE` | Profilo di deployment (`dev`, `staging`, `prod`). Controlla CORS, auth, log level. | `prod` |
| `AUTH_ENABLED` | Abilita/disabilita l'autenticazione. | `true` |
| `AUTH_USERNAME` | Username per l'accesso. | `admin` |
| `AUTH_PASSWORD` | Password per l'accesso. | **Obbligatoria** |
| `AUTH_SECRET` | Chiave segreta per la firma dei token di sessione (HMAC). | **Obbligatoria** |
| `REDIS_PASSWORD` | Password per l'accesso a Redis. | **Obbligatoria** |
| `WEB_CONCURRENCY` | Numero di worker Uvicorn. Aumentare solo con Redis abilitato. | `1` |
| `PROD_FRONTEND_URL` | URL pubblico del frontend (per CORS in produzione). | `""` |

---

## 🛡️ Sicurezza

- **Autenticazione**: Basata su session token JWT firmati con `AUTH_SECRET` e veicolati tramite cookie `HttpOnly` e `Secure`.
- **CSRF Protection**: Token "Double Submit Cookie" validato per tutte le richieste non-idempotenti.
- **Information Leakage**: Un global exception handler impedisce che dettagli di errori interni vengano esposti nelle risposte API.
- **Rate Limiting**: Il backend usa un rate limiter Redis-backed per endpoint sensibili. nginx fornisce un ulteriore livello di protezione a livello IP.
- **CORS**: Configurata in modo restrittivo per il profilo `prod`, consentendo solo `PROD_FRONTEND_URL`.

---

## 🔧 Sviluppo

### Test

La suite di test (basata su `pytest`) copre unità, integrazione e funzionalità end-to-end.

```bash
# Eseguire tutti i test (esclusi quelli marcati come 'integration')
make test

# Eseguire i test e generare un report di coverage
make coverage
```

### Linting

Il progetto usa `pyflakes` per il linting del codice Python e `eslint` per il frontend.

```bash
# Verificare il backend
make lint-backend

# Verificare il frontend
make lint-frontend
```
