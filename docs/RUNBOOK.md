# Production Runbook

Questo documento descrive le procedure operative per il deployment, la gestione e il monitoraggio dell'applicazione in un ambiente di produzione.

## 1. Deployment

Il deployment in produzione è gestito tramite Docker Compose. Assicurarsi che `docker` e `docker-compose` siano installati sul server di destinazione.

### Prerequisiti

1.  **Clonare il repository:**
    ```bash
    git clone https://github.com/3n1gm496/pseudonymization-tool.git
    cd pseudonymization-tool
    ```

2.  **Creare il file `.env`:**
    Copiare `.env.example` in `.env` e compilare tutte le variabili richieste. **Non committare mai il file `.env` nel repository.**

    ```bash
    cp .env.example .env
    nano .env
    ```

    Variabili critiche da impostare:

    | Variabile | Descrizione |
    |---|---|
    | `SECRET_KEY` | Chiave segreta per la firma dei JWT. Deve essere una stringa lunga e casuale. |
    | `ENCRYPTION_KEY` | Chiave a 32 byte (formato hex) per la cifratura AES-256-GCM delle passphrase. |
    | `CORS_ORIGINS_PROD` | Lista di origini consentite per le richieste CORS in produzione (es. `https://app.example.com`). |
    | `LDAP_BIND_PASSWORD` | Password per l'account di servizio LDAP, se usato. |

### Avvio dell'applicazione

Utilizzare Docker Compose per avviare l'applicazione in modalità detached:

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Questo comando:
- Usa `docker-compose.prod.yml` per sovrascrivere le impostazioni di sviluppo.
- Esegue il build delle immagini Docker.
- Avvia i container in background (`-d`).

### Verifica del deployment

1.  **Controllare i log:**
    ```bash
    docker-compose logs -f backend
    ```
    Verificare che non ci siano errori all'avvio.

2.  **Controllare gli health check:**
    Accedere all'endpoint `/api/ready` per verificare che tutti i servizi siano pronti.

    ```bash
    curl http://localhost:8000/api/ready
    ```

    Il risultato dovrebbe essere `{"status":"ready", ...}` con codice 200.

## 2. Monitoraggio

### Health & Readiness Probes

-   **`/api/health`**: Controlla lo stato di base dell'applicazione (risponde 200 OK se l'app è in esecuzione).
-   **`/api/ready`**: Controlla che tutte le dipendenze (Redis, directory temporanee) siano pronte. Usare questo endpoint per i readiness probe di Kubernetes o altri orchestrator.

### Logging

In produzione, il backend è configurato per loggare in formato JSON a livello `INFO`. I log vengono inviati a `stdout` e possono essere raccolti da un aggregatore di log come Fluentd, Logstash o direttamente da Docker.

## 3. Procedure di emergenza

### Riavvio di un servizio

Se un servizio non risponde correttamente, è possibile riavviarlo singolarmente:

```bash
docker-compose restart <service_name>  # es. backend, frontend, redis
```

### Rollback

In caso di deployment fallito, è possibile tornare alla versione precedente del codice e rieseguire il deployment:

1.  Tornare al commit precedente:
    ```bash
    git checkout <commit_hash_precedente>
    ```

2.  Eseguire nuovamente il build e il deployment:
    ```bash
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
    ```

## 4. Backup e ripristino

L'applicazione è stateless, ma Redis contiene dati di sessione e cache. Per il backup di Redis, fare riferimento alla documentazione ufficiale di Redis per le strategie di snapshotting (RDB) o AOF.

## 5. Aggiornamenti

Per aggiornare l'applicazione a una nuova versione:

1.  **Scaricare le modifiche:**
    ```bash
    git pull origin main
    ```

2.  **Eseguire il build e il deployment:**
    ```bash
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
    ```

Docker Compose si occuperà di ricreare solo i container che sono cambiati.
