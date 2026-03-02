# Piano di Test e Metriche

**Autore:** Team Engineering
**Versione:** 4.0.4
**Data:** 2026-03-02

---

## 1. Obiettivi del Test

✅ **COMPLETATI:**
- Coprire moduli critici (auth, crypto, schemas, batch_manager)
- Validare API contract
- Stress test concurrency (10-thread)
- Integration test end-to-end
- Code coverage target > 50% (raggiunto 58.76%)

---

## 2. Risultati Attuali

### Test Suite Status

```
═══════════════════════════════════════════════════════════════
📊 RISULTATI FINALI (2026-03-02)
═══════════════════════════════════════════════════════════════

✅ Tests Passed:       179/179 (100%)
⏭️  Skipped:          9 (expected - slow tests)
❌ Failed:            0
📈 Total Coverage:    58.76%
⏱️  Execution Time:   16.70s

═══════════════════════════════════════════════════════════════
```

### Coverage Detail (Focus Modules)

| Module | Stmts | Miss | Cover | Status |
|--------|-------|------|-------|--------|
| `auth.py` | 96 | 8 | **91.67%** | 🟢 Excellent |
| `crypto.py` | 59 | 3 | **94.92%** | 🟢 Excellent |
| `schemas.py` | 199 | 7 | **96.48%** | 🟢 Excellent |
| `batch_manager.py` | 167 | 59 | **64.67%** | 🟡 Good |
| `rate_limit.py` | 80 | 9 | **88.75%** | 🟢 Excellent |
| `pipeline.py` | 183 | 102 | 44.26% | 🟡 Medium |
| **TOTAL** | **3967** | **1636** | **58.76%** | 🟡 |

### Test Categories

**Critical Bug Fixes (11 tests):**
- Session memory leak (auth.py) - 2 tests
- TOCTOU race condition (batch_manager) - 4 tests
- Thread safety (batch_manager) - 5 tests

**API Contract (25+ tests):**
- Health endpoint ✅
- Ready endpoint ✅
- Policy preview endpoints ✅
- Batch CRUD ✅

**Functional (140+ tests):**
- Document parsing (PDF, DOCX, XLSX, IMG)
- Entity detection (regex, dict, NER)
- Pseudonymization engine
- Report generation
- Rate limiting
- Revert flows (text, batch ZIP)

**Integration (15+ tests):**
- End-to-end pseudonymization
- Clean batch cleanup
- Concurrent batch processing
- Memory leak validation (10-thread stress test)

---

## 3. Coverage Analysis by Module

### 🟢 Critical Modules (>90% Coverage)

**auth.py (91.67%)** - Session management, validation
- Missing: Edge cases in legacy session cleanup

**crypto.py (94.92%)** - AES-256-GCM encryption
- Missing: Legacy format compatibility paths

**schemas.py (96.48%)** - Pydantic data models
- Well-covered request/response validation

### 🟡 Core Business Logic (50-80%)

**batch_manager.py (64.67%)** - Batch lifecycle
- Well-covered: CRUD, cleanup, thread-safety
- Missing: Some error recovery paths

**rate_limit.py (88.75%)** - Rate limiting
- Well-covered: Enforcement, LRU eviction
- Missing: Some configuration edge cases

### 🟠 Lower Priority (< 50% Coverage)

**pipeline.py (44.26%)** - Detection+rename pipeline
- Complex conditional paths, future focus

**revert.py (48.51%)** - ZIP batch revert
- Functional coverage adequate, edge cases missing

---

## 4. Code Quality Gates

✅ **ALL PASSING:**
- No lint errors (flake8, ruff)
- Type checking (mypy) - 0 errors
- Security scan (bandit) - 0 critical issues
- Complexity (radon) - All functions < 10 complexity

---

## 5. Test Execution

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest backend/tests/test_api_contract.py -v

# Run specific test category
pytest backend/tests/test_additional_fixes.py -v  # Critical bug fixes
pytest backend/tests/test_revert_text.py -v      # Revert flows

# Stress test (10-thread concurrency)
pytest backend/tests/test_rate_limit.py::test_concurrent_requests_thread_safe -v
```

---

## 6. Regression Prevention

**Automated checks on every commit:**
- All 179 tests must pass
- Coverage must not decrease below 58.76%
- No new security issues (bandit)

---

## 7. Next Steps (Phase 2+)

- [ ] Increase pipeline.py coverage to 70%+ (complex detection logic)
- [ ] Add stress tests for large batch processing (>1000 files)
- [ ] E2E tests with real Selenium/browser automation
- [ ] Performance benchmarks (file parsing speed)
- [ ] Load testing (concurrent users)

---

## 8. Known Limitations

- **skip=slow tests** (9) - Database operations, file I/O heavy tests run separately
- **OCR coverage** - Image parsing relies on external Tesseract, tested on sample images only
- **Network tests** - All tests are offline, no network I/O

---

**Last Updated:** 2026-03-02  
**Test Framework:** pytest 9.0.2  
**Python Version:** 3.12.3

L'obiettivo della fase di test è garantire che la versione MVP del Local Pseudonymization Tool sia **funzionale, sicura e robusta** prima del rilascio. I test verificheranno che tutti i requisiti funzionali e non funzionali siano stati rispettati, con un'enfasi particolare sulla corretta gestione dei dati sensibili e sulla sicurezza operativa dell'applicazione.

## 2. Strategia di Test

La strategia prevede diversi livelli di test che verranno eseguiti nell'ambiente di sviluppo prima del packaging finale.

- **Test Unitari (Unit Tests):** Focalizzati su singole funzioni e moduli (es. un singolo detector regex, la funzione di cifratura).
- **Test di Integrazione (Integration Tests):** Verificheranno l'interazione tra i diversi moduli della pipeline (es. Parser -> Detector -> Pseudonymizer).
- **Test End-to-End (E2E Tests):** Simuleranno l'intero workflow dell'utente, dall'upload del file al download dell'output, interagendo con le API del backend.
- **Test di Sicurezza Manuali:** Verifiche mirate per confermare l'aderenza ai vincoli di sicurezza.

## 3. Piano di Test Dettagliato (MVP)

### 3.1. Test Funzionali per Formato

Per ogni formato supportato, verrà creato un file di test contenente un mix di entità sensibili.

| Caso di Test | Descrizione | Criterio di Successo Atteso |
|---|---|---|
| **TC-FUNC-01 (TXT/MD/CSV)** | Processare un file di testo semplice contenente email, IP, e nomi. | Il file di output contiene gli pseudonimi corretti. Il report elenca tutti i finding. |
| **TC-FUNC-02 (DOCX)** | Processare un file `.docx` con testo nel corpo, header e footer. | Il testo viene estratto e pseudonimizzato correttamente. Gli elementi non testuali rimangono inalterati. |
| **TC-FUNC-03 (XLSX)** | Processare un file `.xlsx` con celle di testo e celle contenenti formule. | Solo le celle di testo vengono modificate. Le formule rimangono intatte. Il report segnala le formule ignorate. |
| **TC-FUNC-04 (PDF Testuale)** | Processare un PDF nativamente testuale. | Il testo viene estratto e pseudonimizzato. L'output è un nuovo file di testo o un PDF con il testo sostituito (da definire). |
| **TC-FUNC-05 (PDF non Testuale)** | Tentare di processare un PDF basato su immagini o cifrato. | Il sistema rileva che il testo non è estraibile e marca il file con un warning chiaro nel report finale. |
| **TC-FUNC-06 (JPG/PNG)** | Processare un'immagine (es. screenshot) con testo visibile. | L'OCR locale estrae il testo. Le entità vengono rilevate. L'immagine di output presenta rettangoli di redazione sulle aree sensibili. I metadati EXIF sono rimossi. |

### 3.2. Test del Workflow

| Caso di Test | Descrizione | Criterio di Successo Atteso |
|---|---|---|
| **TC-WF-01 (Review Flow)** | Eseguire un batch, e nella schermata di review: accettare un finding, escluderne un altro, modificarne un terzo. | Le decisioni dell'utente vengono rispettate nel file di output finale. |
| **TC-WF-02 (Consistenza Batch)** | Processare un batch con più file dove la stessa entità (es. stessa email) appare più volte. | L'entità riceve sempre lo stesso pseudonimo in tutti i file del batch. |
| **TC-WF-03 (Light vs. Strict)** | Processare lo stesso file prima in modalità `Light` e poi `Strict`. | Gli pseudonimi generati rispettano le policy definite per ciascuna modalità. |
| **TC-WF-04 (Mapping Cifrato)** | Eseguire un batch, ottenere il file `mapping.enc`. Eseguire un secondo processo (simulato) per decifrarlo con la passphrase corretta e una sbagliata. | La decifratura ha successo solo con la passphrase corretta. |
| **TC-WF-05 (Dry-Run)** | Eseguire un batch in modalità dry-run. | Il sistema produce un report con i finding ma non genera file di output modificati. |

### 3.3. Test di Sicurezza e Robustezza

| Caso di Test | Descrizione | Criterio di Successo Atteso |
|---|---|---|
| **TC-SEC-01 (No Network Calls)** | Monitorare il traffico di rete dell'applicazione durante l'elaborazione di un batch. | Nessuna chiamata HTTP/TCP in uscita viene iniziata dal processo Python. |
| **TC-SEC-02 (Cleanup Temp)** | Controllare la directory dei file temporanei dopo il completamento (con successo e con errore) di un batch. | La directory specifica del batch viene eliminata completamente. |
| **TC-SEC-03 (Error Handling)** | Processare un file corrotto o in un formato non supportato. | L'applicazione non crasha e riporta un errore specifico per quel file nel report finale. |

## 4. Dataset di Test

Verrà creato un dataset di file sintetici ma realistici per coprire tutti i casi di test. Questo includerà:

- File di log con IP e hostname.
- Documenti di policy con email, nomi e codici fiscali.
- Fogli di calcolo con dati anagrafici misti a formule.
- Screenshot di interfacce utente e terminali.
- Un dizionario custom con sigle di progetto inventate.

## 5. Metriche di Successo (MVP)

| Metrica | Obiettivo (MVP) | Come viene misurata |
|---|---|---|
| **Copertura Funzionale** | 100% dei casi di test funzionali e di workflow superati. | Esecuzione del piano di test. |
| **Precisione dei Detector** | > 95% per detector basati su regex ad alta confidenza (Email, IP, CF). | Analisi manuale dei risultati su un dataset di validazione. |
| **Assenza di Regressioni** | 0 regressioni critiche introdotte durante lo sviluppo. | Esecuzione di un set di test di regressione prima di ogni rilascio. |
| **Conformità alla Sicurezza** | 100% dei test di sicurezza superati. | Ispezione manuale e uso di tool di monitoraggio. |
| **Performance Indicativa** | Elaborazione di un batch di medie dimensioni (5 file, ~10MB totali) in un tempo ragionevole (< 60 secondi) su una macchina standard. | Misurazioni cronometrate durante i test E2E. |
