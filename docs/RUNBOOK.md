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

### Decisione architetturale: Redis senza persistenza AOF

Redis viene usato in questo progetto come **broker Celery, session store e rate limiter**. I dati che gestisce sono **volatili per scelta consapevole**:

| Dato | Dove è persistito | Impatto riavvio Redis |
|------|-------------------|-----------------------|
| Sessioni utente | Redis (TTL 8h) | Utenti disconnessi, re-login richiesto |
| Task Celery in coda | Redis (broker) | Task persi se non ancora avviati |
| Contatori rate limiter | Redis (finestra mobile) | Reset contatori (comportamento sicuro) |
| Dati batch (file, findings) | Filesystem `STATE_DIR` | **Nessun impatto** |
| Mappings di cifratura | Filesystem `STATE_DIR` | **Nessun impatto** |

**Conclusione:** un riavvio Redis causa solo la disconnessione degli utenti attivi. I dati applicativi (batch, file pseudonimizzati, chiavi di cifratura) sono persistiti sul volume Docker `app_state` e non vengono persi.

La persistenza AOF (`--appendonly yes`) **non è abilitata di default** perché:
- Aggiunge latenza I/O su ogni scrittura.
- Non è necessaria per i dati transitori gestiti da questo tool.
- Aumenta la complessità operativa (rotazione log AOF, `BGREWRITEAOF`).

**Per abilitare AOF** in ambienti con requisiti di durabilità elevati (es. sessioni SSO di lunga durata), modificare il comando Redis in `docker-compose.yml`:

```yaml
command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}",
          "--appendonly", "yes", "--appendfsync", "everysec"]
```

### Backup dei dati applicativi

I dati critici risiedono nel volume Docker `app_state`. Per eseguire un backup:

```bash
# Backup del volume app_state (batch, mappings, chiavi)
docker run --rm \
  -v pseudonymization-tool_app_state:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/app_state_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Ripristino
docker run --rm \
  -v pseudonymization-tool_app_state:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/app_state_<timestamp>.tar.gz -C /data
```

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

## 6. Gestione Utenti e Autenticazione

### 6.1. Sistema Multi-Utente (Locale)

#### Bootstrap al primo avvio

Al primo avvio, se `STATE_DIR/users.db` non esiste, il sistema crea automaticamente un utente `admin` con una **password generata casualmente**. La password è visibile nel log di avvio:

```
[WARNING] user_manager: ⚠️  BOOTSTRAP — admin creato con password generata: 'XXXX' — CAMBIARE IMMEDIATAMENTE
```

**Azione richiesta:** Accedere con questa password e cambiarla immediatamente da **Impostazioni → Utenti → Modifica password**.

#### Ruoli disponibili

| Ruolo | Permessi |
|-------|----------|
| `admin` | Accesso completo: scan, apply, download, impostazioni, gestione utenti |
| `operator` | Accesso operativo: scan, review, apply, download. Non può accedere alle impostazioni di sistema né gestire utenti |

#### Operazioni via UI

Tutte le operazioni di gestione utenti sono disponibili in **Impostazioni → Utenti** (solo per utenti con ruolo `admin`):

- **Crea utente**: Inserire username, password (min 8 caratteri) e ruolo
- **Modifica ruolo**: Cambiare il ruolo di un utente esistente
- **Modifica password**: Cambiare la password di un utente
- **Elimina utente**: Eliminare un utente (non è possibile eliminare l'ultimo admin)

#### Reset password admin via CLI

Se si perde l'accesso all'account admin, è possibile resettare la password direttamente nel database SQLite:

```bash
# Accedere al container backend
docker exec -it pseudonymization-tool-backend-1 bash

# Generare un hash bcrypt per la nuova password
python3 -c "import bcrypt; print(bcrypt.hashpw(b'NuovaPassword123!', bcrypt.gensalt()).decode())"

# Aggiornare il database (sostituire HASH_QUI con l'hash generato sopra)
python3 -c "
import sqlite3, os
db = os.path.join(os.environ.get('PSEUDONYMIZER_STATE_DIR', '/app/state'), 'users.db')
conn = sqlite3.connect(db)
conn.execute(\"UPDATE users SET password_hash=? WHERE username='admin'\", ('HASH_QUI',))
conn.commit()
conn.close()
print('Password aggiornata')
"
```

### 6.2. Autenticazione LDAP

L'applicazione supporta un'autenticazione ibrida, permettendo agli utenti di autenticarsi sia tramite il database locale che tramite un server LDAP (es. Active Directory, eDirectory).

#### Configurazione

La configurazione LDAP avviene tramite la UI in **Impostazioni → LDAP** o tramite variabili d'ambiente nel file `.env`.

| Variabile | UI Label | Descrizione |
|---|---|---|
| `LDAP_AUTH_ENABLED` | Abilita Autenticazione LDAP | Abilita/disabilita l'opzione di login LDAP. |
| `LDAP_HOST` | Host | Indirizzo IP o FQDN del server LDAP. |
| `LDAP_PORT` | Porta | Porta del server LDAP (es. 389 o 636 per LDAPS). |
| `LDAP_USE_SSL` | Usa SSL | Abilita la connessione sicura LDAPS. |
| `LDAP_TLS_VALIDATE_CERT` | Valida Certificato TLS | Se `true`, valida il certificato del server LDAP. |
| `LDAP_BIND_DN` | Bind DN | DN dell'utente di servizio per la connessione iniziale. |
| `LDAP_BIND_PASSWORD` | Bind Password | Password dell'utente di servizio. |
| `LDAP_USER_BASE_DN` | Base DN Utenti | Base DN per la ricerca degli utenti. |
| `LDAP_ADMIN_GROUP_DN` | DN Gruppo Admin | DN del gruppo LDAP per il ruolo `admin`. |
| `LDAP_OPERATOR_GROUP_DN` | DN Gruppo Operator | DN del gruppo LDAP per il ruolo `operator`. |
| `LDAP_DEFAULT_ROLE` | Ruolo di Default | Ruolo assegnato se l'utente non appartiene a nessun gruppo mappato. |

#### Flusso di Autenticazione

1.  L'utente seleziona "Aziendale (LDAP)" nella pagina di login.
2.  Il sistema si connette al server LDAP usando il Bind DN e la password di servizio.
3.  Cerca l'utente inserito nel `LDAP_USER_BASE_DN` usando il filtro `(&(objectClass=inetOrgPerson)(cn=<username>))`.
4.  Se l'utente viene trovato, il sistema tenta di eseguire un bind con il DN dell'utente e la password fornita.
5.  Se il bind ha successo, l'utente è autenticato. Il sistema verifica l'appartenenza ai gruppi (`LDAP_ADMIN_GROUP_DN`, `LDAP_OPERATOR_GROUP_DN`) per assegnare il ruolo corretto.

### 6.3. Backup del database utenti

Il database utenti è incluso nel backup del volume `app_state` (vedi sezione 4). Il file è `STATE_DIR/users.db`.

```bash
# Backup specifico del database utenti
docker run --rm \
  -v pseudonymization-tool_app_state:/data \
  -v $(pwd)/backups:/backup \
  alpine cp /data/users.db /backup/users_$(date +%Y%m%d_%H%M%S).db
```

## 7. Notifiche Real-time (SSE)

L'applicazione utilizza Server-Sent Events (SSE) per notificare al frontend gli aggiornamenti di stato dei batch di pseudonimizzazione in tempo reale.

### Funzionamento

-   Quando un utente visualizza un batch in elaborazione, il frontend apre una connessione `EventSource` all'endpoint `/api/batches/{batch_id}/events`.
-   Il backend tiene aperta la connessione e invia eventi (`message`) ogni volta che lo stato del batch cambia (`processing`, `done`, `error`).
-   Questo elimina la necessità di polling continuo, riducendo il carico sul server e fornendo un'esperienza utente più reattiva.

### Troubleshooting

-   **Problemi di connessione:** Verificare che nessun firewall o reverse proxy intermedio blocchi le connessioni `text/event-stream` o le mantenga aperte per troppo poco tempo. La configurazione nginx fornita (`proxy_buffering off;`) è già ottimizzata per SSE.
-   **Fallback a Polling:** Se la connessione SSE fallisce, il frontend esegue automaticamente un fallback a polling tradizionale (una richiesta `GET /api/batches/{batch_id}/status` ogni 5 secondi), garantendo la continuità operativa.
