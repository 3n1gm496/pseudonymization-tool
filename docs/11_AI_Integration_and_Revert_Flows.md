# AI Integration e Flussi di Revert

**Documento:** Guida per l'integrazione con AI e decifratura di risposte  
**Versione:** 4.1+  
**Target Audience:** Data Engineers, Security Analysts, AI Integration Developers

---

## 📌 Indice

1. [Overview](#overview)
2. [Flusso "Prepara per AI"](#flusso-prepara-per-ai)
3. [Flusso "Decifera Risposta AI"](#flusso-decifera-risposta-ai)
4. [Flusso "Revert Batch ZIP"](#flusso-revert-batch-zip)
5. [Sicurezza e Passphrase](#sicurezza-e-passphrase)
6. [Workflow Completo Esempio](#workflow-completo-esempio)
7. [Troubleshooting](#troubleshooting)

---

## Overview

La **pseudonimizzazione** trasforma dati sensibili in valori placeholder (es: `mario.rossi@acme.com` → `EMAIL_001`). Il Pseudonymization Tool fornisce tre flussi per lavorare con AI:

| Flusso | Quando usarlo | Input | Output |
|--------|--------------|-------|--------|
| **Prepara per AI** | Generi testo pseudonimo da inviare a modello AI | Testo pseudonimo + passphrase | Testo + mapping.enc |
| **Decifera Risposta** | La ricezione una risposta dall'AI (contiene pseudonimi) | Testo AI + mapping.enc + passphrase | Testo decifrato originale |
| **Revert Batch ZIP** | Devi invertire l'intera pseudonimizzazione di un batch | ZIP da batch | ZIP revertito |

### Caso d'uso tipico:

```
1. Carica dati sensibili nel Tool
   ↓
2. Seleziona "Pseudonimizza" → scarica testo pseudonimo + mapping.enc
   ↓
3. Invia testo pseudonimo all'AI (es: ChatGPT, Claude)
   ↓
4. L'AI risponde con testo che contiene i tuoi pseudonimi
   ↓
5. Usa "Decifera Risposta AI" con mapping.enc + passphrase
   ↓
6. Ricevi risposta originaletxt (con dati originali reintegrati)
```

---

## Flusso "Prepara per AI"

### Quando usare questo flusso

- **Scenario:** Vuoi inviare dati sensibili a un modello AI (ChatGPT, Claude, LLaMA, ecc.)
- **Problema:** Non puoi riversare i dati originali a terzi
- **Soluzione:** Pseudonimizza localmente, invia solo i placeholder

### Step-by-step

#### Passo 1: Seleziona "Prepara per AI" nel Menu

Nel **RevertPanel** (sezione destra), clicca su **"Prepara per AI"**.

```
┌─ Pseudonymization Tool ─────────────────────┐
│                                             │
│  [Scanner]   [Review]   [Results]          │
│                                             │
│  [Revert Panel]  ← A DESTRA                │
│   - Prepara per AI    ← CLICCA QUI         │
│   - Decifera Risposta                      │
│   - Revert Batch ZIP                       │
│                                             │
└─────────────────────────────────────────────┘
```

#### Passo 2: Seleziona un Batch Completato

Il tab "Prepara per AI" mostra un selector:
```
Seleziona batch pseudonimizzato
[Dropdown con elenco batch]
```

**Seleziona il batch** su cui hai già applicato la pseudonimizzazione.

#### Passo 3: Visualizza il Testo Pseudonimizzato

Una volta selezionato il batch, vedrai:

```
┌─ TESTO PSEUDONIMIZZATO ─────────────────────┐
│                                             │
│ L'utente EMAIL_001 ha creato un progetto    │
│ CUSTOM_001 presso IPV4_001 il 2026-02-28   │
│                                             │
│ [Copia negli Appunti]                       │
│                                             │
└─────────────────────────────────────────────┘
```

Clicca **"Copia negli Appunti"** per copiare il testo.

#### Passo 4: Scarica il File Mapping Cifrato

Nella sezione seguente, vedrai:

```
┌─ FILE MAPPING (CIFRATO) ─────────────────────┐
│                                             │
│ mapping_<batch_id>.enc                      │
│                                             │
│ [⬇️ Scarica Mapping]                       │
│                                             │
│ ⚠️ Questo file contiene le corrispondenze: │
│ EMAIL_001 ↔ mario.rossi@acme.com (CIFRATO) │
│                                             │
└─────────────────────────────────────────────┘
```

Clicca **"⬇️ Scarica Mapping"** e salva il file. **Conservalo al sicuro.**

#### Passo 5: Copia la Passphrase di Decifrazione

Infine, vedrai la passphrase che hai inserito durante la pseudonimizzazione:

```
┌─ PASSPHRASE DI DECIFRAZIONE ─────────────────┐
│                                             │
│ SuperSecurePassword123!@#                   │
│                                             │
│ [Copia Passphrase]                          │
│                                             │
│ ⚠️ Conserva questa passphrase al sicuro:    │
│ servirà per decifrare il mapping.enc        │
│                                             │
└────────────────────────────────────────────┘
```

**NON inviare la passphrase all'AI.**

### Riepilogo "Prepara per AI"

Ora hai tre artefatti:
1. **Testo pseudonimizzato** - Da inviare all'AI
2. **mapping.enc** - File cifrato (conservare al sicuro)
3. **Passphrase** - Necessaria per decifrare (conservare al sicuro)

---

## Flusso "Decifera Risposta AI"

### Quando usare questo flusso

- **Scenario:** L'AI ha processato il tuo testo pseudonimizzato e ha risposto (es: "EMAIL_001 ha ricevuto la conferma il 2026-02-28")
- **Problema:** La risposta contiene pseudonimi, non dati leggibili
- **Soluzione:** Usa il mapping.enc per reintegrar i dati originali

### Step-by-step

#### Passo 1: Seleziona "Decifera Risposta AI"

Nel **RevertPanel**, clicca su **"Decifera Risposta AI"**.

#### Passo 2: Carica il File mapping.enc

Vedrai una sezione:
```
┌─ CARICA FILE MAPPING (CIFRATO) ──────────────┐
│                                             │
│ [Scegli file mapping.enc...]                │
│                                             │
│ Accettati: *.enc                            │
│                                             │
└─────────────────────────────────────────────┘
```

Clicca e **seleziona il file mapping.enc** che hai scaricato in "Prepara per AI".

#### Passo 3: Inserisci la Passphrase

```
┌─ PASSPHRASE ─────────────────────────────────┐
│                                             │
│ Inserisci passphrase di decifrazione:       │
│ [________________________] (nascosta)        │
│                                             │
└─────────────────────────────────────────────┘
```

Incolla la passphrase che avevi salvato.

#### Passo 4: Incolla la Risposta dell'AI

```
┌─ TESTO PSEUDONIMIZZATO (RISPOSTA AI)──────────┐
│                                             │
│ Incolla la risposta dell'AI:                │
│                                             │
│ ┌──────────────────────────────────────┐    │
│ │ EMAIL_001 ha ricevuto la conferma    │    │
│ │ il 2026-02-28 presso CUSTOM_001      │    │
│ └──────────────────────────────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
```

#### Passo 5: Visualizza Anteprima (Preview)

Clicca **"Anteprima Decifratura"**:

```
┌─ ANALISI PREVIEW ────────────────────────────┐
│                                             │
│ Mappature nel file:   3 entità              │
│ Caratteri testo:      147                   │
│ Pseudonimi trovati:   2 match               │
│                                             │
│ [EMAIL_001 → mario.rossi@acme.com]          │
│ [CUSTOM_001 → ACME Corp]                    │
│                                             │
└─────────────────────────────────────────────┘
```

Se il preview mostra i tuoi pseudonimi, significa che la passphrase è corretta. ✓

#### Passo 6: Applica la Decifratura

Clicca **"Decifera Risposta"**:

```
┌─ RISPOSTA DECIFRATA ─────────────────────────┐
│                                             │
│ mario.rossi@acme.com ha ricevuto la        │
│ conferma il 2026-02-28 presso ACME Corp    │
│                                             │
│ [Copia negli Appunti]                       │
│                                             │
└─────────────────────────────────────────────┘
```

✓ Adesso hai la risposta dell'AI con i dati originali reintegrati!

---

## Flusso "Revert Batch ZIP"

### Quando usare questo flusso

- **Scenario:** Hai un file ZIP di un batch pseudonimizzato e vuoi invertire completamente il processo
- **Problema:** Hai molti file in ZIP e vuoi re-originarli tutti in una volta
- **Soluzione:** Carica lo ZIP + mapping.enc + passphrase

### Step-by-step

#### Passo 1: Seleziona "Revert Batch ZIP"

Nel **RevertPanel**, clicca su **"Revert Batch ZIP"**.

#### Passo 2: Carica lo ZIP di Batch

```
┌─ CARICA BATCH ZIP ───────────────────────────┐
│                                             │
│ [Scegli file batch ZIP...]                  │
│                                             │
│ File ZIP deve contenere:                    │
│ - files/ (i file pseudonimizzati)           │
│ - mapping.enc (il file di mapping)          │
│                                             │
└─────────────────────────────────────────────┘
```

Seleziona lo ZIP scaricato dalla UI dopo l'apply.

#### Passo 3: Inserisci Passphrase

Come nel flusso "Decifera Risposta", inserisci la passphrase.

#### Passo 4: Visualizza Preview

```
┌─ ANTEPRIMA REVERT ───────────────────────────┐
│                                             │
│ File ZIP scansionati:   1                   │
│ File di testo trovati:  1                   │
│ Pseudonimi da revert:   3                   │
│ Sostituzioni previste:  5                   │
│                                             │
└─────────────────────────────────────────────┘
```

#### Passo 5: Applica Revert

Clicca **"Applica Revert"** → scarica lo ZIP fatto di nuovo con i dati originali.

---

## Sicurezza e Passphrase

### Come Scegliere una Passphrase Robusta

La passphrase è la **chiave che cifra il file mapping.enc**. Se qualcuno ruba il mapping.enc, senza la passphrase non può leggerlo.

#### ✅ BUONE passphrase

```
SuperSecurePassword123!@#        (lunghezza: 27, entropia: 4.2 bit/char)
MyC@t'sNameIs$Fluffy#2026      (lunghezza: 30, entropia: 4.8 bit/char)
!@#$%^&*()_+ABCDEFGH_12345     (lunghezza: 32, entropia: 5.1 bit/char)
```

#### ❌ CATTIVE passphrase

```
password                          (too weak, dictionary word)
12345678                          (only numbers, low entropy)
mario                             (single name, low entropy)
```

#### Raccomandazioni

1. **Lunghezza minima:** 12 caratteri (consigliato: 20+)
2. **Caratteri misti:** maiuscole, minuscole, numeri, simboli
3. **No parole comuni:** evita nomi, date di compleanno, parole di dizionario
4. **Unica per batch:** usa una passphrase diversa per ogni batch sensibile
5. **Salva in sicurezza:** usa un password manager (1Password, Bitwarden, KeePass)

**Il Tool valida automaticamente l'entropia.** Se la passphrase è debole, riceverai un avviso.

### Cosa Succede se Perdi la Passphrase

- ❌ **Non puoi decifrare il mapping.enc**
- ❌ **I dati originali rimangono persi** (i pseudonimi rimangono)
- ✅ Ma il file mapping.enc rimane cifrato (sicuro da attacchi)

**Conserva la passphrase in un luogo sicuro.** Se è critica, usa un password manager con backup cifrato.

---

## Workflow Completo Esempio

Scenario: Un'azienda vuole analizzare 500 email di supporto con ChatGPT per sentiment analysis, senza esporre PII.

### Setup Iniziale

1. **Carica 500 email nel Tool**
   - Formato: .txt, .csv, .eml
   - Seleziona modalità: `STRICT` (rileva tutte le entità PII)
   - Seleziona policy: `Email Headers`

2. **Scansiona**
   - Tool rileva: 1.250 entità PII (nomi, email, IP, ecc.)
   - Genera pseudonimi: EMAIL_001, PERSON_001, IPV4_001, ecc.

3. **Review e Applica**
   - Review ogni entità (opzionale: modifica pseudonimi)
   - Applica → scarica ZIP con:
     - `files/` → 500 email pseudonimizzate
     - `report.html` → audit trail delle sostituzioni
     - `mapping.enc` → mapping cifrato

### Phase "Prepara per AI"

4. **Estrai una email di campione**
   ```
   Subject: Problema con login
   From: EMAIL_001
   To: EMAIL_002
   
   "Ciao, sono PERSON_001 e non riesco ad accedere da PERSON_002..."
   ```

5. **Scarica mapping.enc e passphrase**
   - mapping.enc: `mapping_batch_xyz.enc`
   - Passphrase: `MyC@t'sNameIs$Fluffy#2026`

### Phase "Invia a ChatGPT"

6. **Paste email pseudonimizzata in ChatGPT**
   ```
   Prompt:
   "Analizza il sentiment di questo ticket di supporto:
   
   Subject: Problema con login
   From: EMAIL_001
   To: EMAIL_002
   
   Ciao, sono PERSON_001 e non riesco ad accedere da PERSON_002..."
   ```

7. **ChatGPT risponde:**
   ```
   Sentiment: NEGATIVO (frustazione moderata)
   
   Azioni consigliate:
   - Contattare EMAIL_001 per verificare credenziali
   - Controllare se PERSON_001 ha 2FA abilitato
   - Resettare password per PERSON_002...
   ```

### Phase "Decifera Risposta AI"

8. **Nel Tool, tab "Decifera Risposta AI":**
   - Carica `mapping_batch_xyz.enc`
   - Inserisci passphrase: `MyC@t'sNameIs$Fluffy#2026`
   - Incolla risposta di ChatGPT
   - Clicca "Decifera"

9. **Ricevi risposta decifrata:**
   ```
   Sentiment: NEGATIVO (frustazione moderata)
   
   Azioni consigliate:
   - Contattare mario.rossi@acme.com per verificare credenziali
   - Controllare se Giovanni Rossi ha 2FA abilitato
   - Resettare password per Maria Bianchi...
   ```

✓ **Fine del workflow.** Ora hai:
- Analisi AI completa
- Risposta con dati originali reintegrati
- Nessun dato PII mai inviato a ChatGPT

---

## Troubleshooting

### Q: "Passphrase non è corretta per questo mapping.enc"

**Problema:** La passphrase che hai inserito non coincide.

**Soluzioni:**
1. ✓ Copia la passphrase da password manager (non digitarla)
2. ✓ Controlla se hai usato MAIUSCOLE/minuscole correttamente
3. ✓ Verifica di aver scaricato il mapping.enc giusto (batch corrispondente)
4. ❌ Se la passphrase è persa: non puoi più decifrare (usa un backup del mapping.enc)

---

### Q: "Il file non è un mapping.enc valido (magic header non riconosciuto)"

**Problema:** Il file che hai scaricato non è un mapping.enc valido.

**Soluzioni:**
1. ✓ Verifica di aver scaricato il file corretto (dovrebbe finire in `.enc`)
2. ✓ Controlla che il file non sia stato corrotto durante download/email
3. ✓ Se è un backup vecchio, potrebbe essere in formato v1 (legacy support)
4. ❌ Se il file è davvero corrotto: scarica di nuovo dal Tool

---

### Q: "Testo troppo lungo"

**Problema:** Il testo che stai decrifrando è > 200.000 caratteri.

**Soluzioni:**
1. ✓ Dividi il testo in sezioni più piccole
2. ✓ Usa "Revert Batch ZIP" per file grandi (supporta fino a 50 MB)
3. ✓ Contatta l'admin se devi aumentare il limite (configurabile)

---

### Q: "Anteprima preview mostra 0 match"

**Problema:** Il Tool non trova pseudonimi nel testo che incollate.

**Soluzioni:**
1. ✓ Verifica di aver incollato il testo dalla risposta dell'AI (non il testo originale)
2. ✓ Controlla che mapping.enc e testo appartengono allo stesso batch
3. ✓ Se l'AI ha modificato i pseudonimi (es: "EMAIL_001" → "email_001"), non verranno trovati (case-sensitive)

---

### Q: "Come posso modificare un pseudonimo prima di mandarla all'AI?"

**Soluzione:**
Durante il flusso "Review" (prima di Applica), clicca su ogni finding e modificalo.
Ad esempio: `EMAIL_001` → `UTENTE_A` (più leggibile per l'AI).

Poi continua con "Prepara per AI" (i pseudonimi modificati saranno nel mapping.enc).

---

## Links Correlati

- [README.md](../README.md) - Installazione e setup
- [docs/06_Detector_Strategy.md](../docs/06_Detector_Strategy.md) - Come il Tool rileva entità PII
- [docs/04_Policies.md](../docs/04_Policies.md) - Cosa rileva ogni politica
- [CRITICAL_ANALYSIS_REPORT.md](../CRITICAL_ANALYSIS_REPORT.md) - Analisi critica del progetto

---

**Last updated:** 28 Feb 2026  
**Tool version:** v4.1+  
**Feedback:** Contatta il team per miglioramenti a questo documento
