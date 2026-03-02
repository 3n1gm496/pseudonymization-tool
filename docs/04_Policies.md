# Policy di Pseudonimizzazione: Light vs. Strict

**Autore:** Manus AI
**Versione:** 4.0.4
**Data:** 2026-03-02

---

## 1. Introduzione

Questo documento definisce il comportamento specifico delle due modalità di pseudonimizzazione, **Light** e **Strict**. L'obiettivo della modalità `Light` è preservare il massimo contesto possibile per l'analisi (es. mantenendo la struttura di un'email o di un IP), mentre la modalità `Strict` mira a ridurre al minimo il rischio di re-identificazione, anche a costo di una minore leggibilità per l'analista.

La scelta della modalità influenza come gli pseudonimi vengono generati per ciascuna categoria di entità.

## 2. Tabella delle Policy per Entità (MVP)

La tabella seguente dettaglia le regole di trasformazione per ogni tipo di entità nelle due modalità. Gli pseudonimi sono consistenti all'interno di un batch (lo stesso valore originale avrà sempre lo stesso pseudonimo).

| Tipo Entità | Esempio Originale | Policy Modalità `Light` | Esempio Output `Light` | Policy Modalità `Strict` | Esempio Output `Strict` | Note |
|---|---|---|---|---|---|---|
| **Email** | `mario.rossi@ente.gov.it` | Sostituisce la parte locale e il dominio con contatori consistenti. Preserva il TLD e la struttura. | `user_001@orgdom_001.gov.it` | Sostituisce l'intera email con un token generico. | `EMAIL_001` | La modalità Light è più utile per analizzare flussi di comunicazione. |
| **IPv4** | `10.24.8.15` | Sostituisce ogni ottetto con un contatore o un valore fisso, preservando la struttura a 4 ottetti. | `10.24.x.x` o `IPV4_SUBNET_001_HOST_001` | Sostituisce l'intero indirizzo con un token generico. | `IPV4_001` | La modalità Light aiuta a tracciare attività dalla stessa subnet. |
| **IPv6** | `2001:0db8:85a3:0000:0000:8a2e:0370:7334` | Sostituisce i segmenti con contatori, mantenendo la struttura. (Best-effort) | `IPV6_PREFIX_001::HOST_001` | Sostituisce l'intero indirizzo con un token generico. | `IPV6_001` | La complessità di IPv6 rende la modalità Strict più sicura e semplice da implementare. |
| **URL** | `https://intranet.ente.gov.it/documenti/riservati` | Sostituisce il dominio e parti del path con contatori, preservando lo schema e la struttura generale. | `https://orgdom_001.gov.it/path_001/path_002` | Sostituisce l'intero URL con un token generico. | `URL_001` | La modalità Light permette di analizzare i pattern di accesso. |
| **Dominio/Hostname** | `server-prod-01.ente.local` | Sostituisce le parti significative con contatori, mantenendo la struttura. | `host_001.orgdom_001.local` | Sostituisce l'intero nome con un token generico. | `HOSTNAME_001` | Utile per distinguere tra diversi sistemi in un log. |
| **Nome/Cognome** | `Mario Rossi` | Sostituisce con un token generico e un contatore. | `PERSON_001` | Identica alla modalità Light. Non c'è un modo sicuro di preservare il formato senza rischiare la re-identificazione. | `PERSON_001` | La distinzione Light/Strict non si applica in modo significativo. |
| **Codice Fiscale** | `RSSMRA80A01H501A` | Sostituisce con un token generico e un contatore. | `CODICE_FISCALE_001` | Identica alla modalità Light. | `CODICE_FISCALE_001` | Dato altamente identificativo, non si tenta di preservarne la struttura. |
| **Partita IVA** | `12345678901` | Sostituisce con un token generico e un contatore. | `PARTITA_IVA_001` | Identica alla modalità Light. | `PARTITA_IVA_001` | Dato altamente identificativo. |
| **Numero Telefono** | `+39 333 1234567` | Sostituisce il numero con un contatore, preservando il prefisso internazionale se presente. | `+39 PHONE_001` | Sostituisce l'intero numero con un token generico. | `PHONE_001` | La modalità Light può aiutare a identificare la provenienza geografica. |
| **Pattern Custom** | `PROGETTO_SEGRETO_2024` | Sostituisce con il nome del dizionario e un contatore. | `CUSTOM_DICT_001_ENTRY_001` | Identica alla modalità Light. | `CUSTOM_DICT_001_ENTRY_001` | Il comportamento è definito dalla natura del dizionario stesso. |

## 3. Logica di Generazione degli Pseudonimi

- **Contatori:** I contatori (es. `_001`, `_002`) sono specifici per tipo di entità e per batch. Ad esempio, la prima email trovata sarà `..._001...`, la seconda `..._002...`, indipendentemente dal suo valore.
- **Mappa di Consistenza:** Durante l'elaborazione di un batch, una mappa in memoria (`{ "valore_originale": "pseudonimo" }`) assicura che lo stesso valore originale riceva sempre lo stesso pseudonimo all'interno dello stesso batch.
- **Prefissi:** I prefissi (`EMAIL_`, `IPV4_`, `PERSON_`) sono costanti e aiutano a mantenere la leggibilità del testo pseudonimizzato, rendendo chiaro quale tipo di dato è stato sostituito.
