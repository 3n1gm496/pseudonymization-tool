# Production Deployment Checklist

Questa checklist deve essere seguita prima di ogni deployment in produzione per garantire che tutti i passaggi critici siano stati completati.

## Fase 1: Preparazione

- [ ] **Codice mergiato su `main`**: Verificare che tutte le feature e i fix siano stati mergiati sul branch `main`.
- [ ] **CI passata su `main`**: Controllare che l'ultima esecuzione della CI su `main` sia verde (test, linting, build, security scan).
- [ ] **Changelog aggiornato**: Verificare che `CHANGELOG.md` sia stato aggiornato con le modifiche della nuova versione.
- [ ] **Variabili d'ambiente pronte**: Preparare i valori per tutte le variabili d'ambiente richieste nel file `.env` di produzione.

## Fase 2: Deployment

- [ ] **Accesso al server di produzione**: Verificare di avere accesso SSH al server di destinazione.
- [ ] **Backup (se necessario)**: Eseguire un backup dei dati persistenti (es. snapshot di Redis) prima dell'aggiornamento.
- [ ] **Clonare/aggiornare il repository**: Eseguire `git pull origin main` sul server di produzione.
- [ ] **Aggiornare il file `.env`**: Modificare il file `.env` con le nuove variabili, se presenti.
- [ ] **Eseguire il deployment con Docker Compose**:
  ```bash
  docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
  ```

## Fase 3: Verifica post-deployment

- [ ] **Controllare i log dei container**: Verificare che non ci siano errori all'avvio.
  ```bash
  docker-compose logs -f backend frontend
  ```
- [ ] **Verificare l'endpoint di readiness**: Assicurarsi che l'applicazione sia pronta a ricevere traffico.
  ```bash
  curl http://localhost:8000/api/ready
  ```
  L'endpoint deve restituire 200 OK.
- [ ] **Testare le funzionalità principali**: Eseguire un test manuale delle funzionalità critiche dell'applicazione (es. login, upload file, scansione).
- [ ] **Monitorare le metriche**: Controllare i dashboard di monitoraggio (se presenti) per verificare che l'applicazione si comporti come previsto (CPU, memoria, latenza).

## Fase 4: Rollback (se necessario)

- [ ] **Identificare il commit di rollback**: Trovare l'hash del commit stabile precedente.
- [ ] **Eseguire il checkout del commit**: `git checkout <commit_hash>`.
- [ ] **Rieseguire il deployment**: `docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
- [ ] **Verificare nuovamente**: Ripetere la Fase 3.
