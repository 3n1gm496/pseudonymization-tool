# AI Integration and Revert Flows

Workflows for preparing pseudonymized data for external AI services and reverting encrypted mappings.

## Table of Contents

1. [Overview](#overview)
2. [Flusso "Pseudonimizza" (Principale)](#flusso-pseudonimizza-principale)
3. [Flusso "Decifra Risposta AI"](#flusso-decifra-risposta-ai)
4. [Flusso "Revert Batch ZIP"](#flusso-revert-batch-zip)
5. [Sicurezza e Passphrase](#sicurezza-e-passphrase)
6. [Workflow Completo Esempio](#workflow-completo-esempio)
7. [Troubleshooting](#troubleshooting)

---

## Overview

Pseudonymization transforms sensitive data into placeholder values (e.g., `mario.rossi@acme.com` → `EMAIL_001`). The tool provides two main workflows after pseudonymization:

| Workflow | When to Use | Input | Output |
|----------|-------------|-------|--------|
| **Decrypt AI Response** | Process AI response containing your pseudonyms | AI output + mapping.enc + passphrase | Decrypted original text |
| **Revert Batch ZIP** | Fully reverse pseudonymization of a batch | Batch ZIP file + mapping.enc + passphrase | Fully reverted ZIP file |

### Typical Workflow

```
1. Upload sensitive data to the tool
   ↓
2. Pseudonymize (Scan → Review → Apply)
   ↓
3. From Results: Download passphrase + mapping.enc + pseudonymized text + ZIP
   ↓
4. [Optional] Send pseudonymized text to external AI
   ↓
5. [If using AI] Use "Decrypt AI Response" to revert output
   OR
   [If batch reversal needed] Use "Revert Batch ZIP" on stored ZIP
```

---

## Flusso "Pseudonimizza" (Principale)

### Quando usare questo flusso

- **Scenario:** Hai completato la pseudonimizzazione (Scansione → Revisione → Applicazione)
- **Risultato:** Ricevi testo pseudonimizzato, passphrase visibile, e file mapping.enc cifrato

### Step-by-step

#### Step 1: Complete Pseudonymization Flow

In the main tool interface:
1. **Scan** — Upload files or text (preset `SOC Logs` applied automatically)
2. **Review** — View and approve/customize finding pseudonyms
3. **Apply** — Generate pseudonymized output

#### Step 2: Access Results Section

After applying, you automatically go to **Results** tab which shows:

```
┌─ RESULTS (Pseudonymization Complete) ──────────────────┐
│                                                         │
│ [Pseudonymized Text area]                              │
│ - Buttons: [Copy] [Scarica TXT]                        │
│ OR                                                      │
│ [Files/Batch Info]                                      │
│ - Button: [Scarica ZIP]                                │
│                                                         │
│ [Stats: # entities, safety label, mode]                │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ 🔐 PASSPHRASE E MAPPING CIFRATO (sezione arancione)    │
│                                                         │
│ Passphrase per Decifrazione:                           │
│ [••••••••••••••••] [👁️] [📋 Copia]                    │
│                                                         │
│ File di Mapping Cifrato:                               │
│ "Scarica questo file per decifrare risposte AI..."    │
│ [📥 Scarica mapping.enc]                               │
│                                                         │
│ ⚠️ Conserva securely file e passphrase                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### Step 3: Copy Passphrase

Click **"👁️"** to show passphrase, then **"📋 Copia"** to copy it.

**Store the passphrase securely.** You'll need it to decrypt AI responses or revert batches later.

#### Step 4: Download Mapping.enc

Click **"📥 Scarica mapping.enc"** to download the encrypted mapping file.

**Important:** This file is encrypted with AES-256-GCM. Without your passphrase, it's unreadable (secure).

#### Step 5: Download Pseudonymized Output

Choose based on your input:

**For text input:**
- Click **"Copia"** to copy pseudonymized text
- Click **"📥 Scarica TXT"** to download as file

**For file input:**
- Click **"📥 Scarica ZIP"** which contains:
  - `files/` — pseudonymized documents
  - `report.html` — audit trail (navigable)
  - `report.json` — structured data
  - `mapping.enc` — encrypted mapping (also in ZIP)

#### Step 6: You Now Have Three Assets

1. **Pseudonymized Text** — Can be sent to external AI services
2. **mapping.enc** — Encrypted mapping (keep safe, don't send to AI)
3. **Passphrase** — Required to decrypt mapping (keep very safe, never send to AI)

### Next Steps

- **Sending to AI?** Send only the pseudonymized text (step 1). Keep mapping.enc and passphrase offline.
- **Got AI Response?** Go to **Revert Panel → Decifra Risposta AI** (see section below)
- **Need to Revert Entire Batch?** Go to **Revert Panel → Revert Batch ZIP** (see section below)

---

## Flusso "Decifra Risposta AI"

### When to Use This Workflow

- **Scenario:** The AI has processed your pseudonymized text and responded (e.g., "EMAIL_001 received confirmation on 2026-02-28")
- **Problem:** The response contains pseudonyms, not readable original data
- **Solution:** Use mapping.enc with your passphrase to restore original data

### Step-by-Step

#### Step 1: Select "Decrypt AI Response"

In the **Revert Panel**, click on **"Decrypt AI Response"**.

#### Step 2: Upload mapping.enc File

You will see a section:
```
┌─ UPLOAD ENCRYPTED MAPPING FILE──────────────┐
│                                             │
│ [Choose mapping.enc file...]                │
│                                             │
│ Accepted: *.enc                             │
│                                             │
└─────────────────────────────────────────────┘
```

Click and **select the mapping.enc file** you downloaded from "Prepare for AI".

#### Step 3: Enter Decryption Passphrase

```
┌─ DECRYPTION PASSPHRASE ───────────────────────┐
│                                             │
│ Enter decryption passphrase:                │
│ [________________________] (hidden)          │
│                                             │
└─────────────────────────────────────────────┘
```

Paste the passphrase you saved earlier.

#### Step 4: Paste AI Response Text

```
┌─ PSEUDONYMIZED AI RESPONSE ──────────────────┐
│                                             │
│ Paste AI response:                          │
│                                             │
│ ┌──────────────────────────────────────┐    │
│ │ EMAIL_001 received confirmation      │    │
│ │ on 2026-02-28 at CUSTOM_001          │    │
│ └──────────────────────────────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
```

#### Step 5: Preview Decryption

Click **"Preview Decryption"**:

```
┌─ PREVIEW ANALYSIS ────────────────────────────┐
│                                             │
│ Mappings in file:        3 entities         │
│ Text characters:         147                 │
│ Pseudonyms found:        2 matches           │
│                                             │
│ [EMAIL_001 → mario.rossi@acme.com]          │
│ [CUSTOM_001 → ACME Corp]                    │
│                                             │
└─────────────────────────────────────────────┘
```

If the preview shows your pseudonyms correctly mapped, your passphrase is correct. ✓

#### Step 6: Apply Decryption

Click **"Decrypt Response"**:

```
┌─ DECRYPTED RESPONSE ─────────────────────────┐
│                                             │
│ mario.rossi@acme.com received confirmation  │
│ on 2026-02-28 at ACME Corp                  │
│                                             │
│ [Copy to Clipboard]                         │
│                                             │
└─────────────────────────────────────────────┘
```

✓ You now have the AI response with original data fully restored!

---

## Flusso "Revert Batch ZIP"

### When to Use This Workflow

- **Scenario:** You have a ZIP file previously downloaded from Results (containing pseudonymized files) and want to fully reverse the pseudonymization
- **Problem:** Files in ZIP need to be de-pseudonymized completely
- **Solution:** Upload ZIP + mapping.enc + passphrase to revert all files at once

### Step-by-Step

#### Step 1: Select "Revert Batch"

In the **Revert Panel**, click on **"Revert Batch"**.

#### Step 2: Upload Batch ZIP

```
┌─ UPLOAD BATCH ZIP ───────────────────────────┐
│                                             │
│ [Choose batch ZIP file...]                  │
│                                             │
│ ZIP must contain:                           │
│ - files/ (pseudonymized files)              │
│ - mapping.enc (mapping file)                │
│                                             │
└─────────────────────────────────────────────┘
```

Select the ZIP file downloaded from the UI after pseudonymization.

#### Step 3: Enter Passphrase

As in the "Decrypt AI Response" workflow, enter your passphrase.

#### Step 4: Preview Revert Results

```
┌─ ANTEPRIMA REVERT ───────────────────────────┐
│                                             │
```
┌─ REVERT PREVIEW ──────────────────────────────┐
│                                             │
│ ZIPfiles scanned:        1                  │
│ Text files found:        1                  │
│ Pseudonyms to revert:    3                  │
│ Replacements planned:    5                  │
│                                             │
└─────────────────────────────────────────────┘
```

#### Step 5: Apply Revert

Click **"Apply Revert"** → download new ZIP with original data restored.

---

## Security and Passphrase

### Choosing a Strong Passphrase

Your passphrase is the **key that encrypts mapping.enc**. If someone obtains mapping.enc without your passphrase, they cannot read it.

#### ✅ STRONG passphrases

```
SuperSecurePassword123!@#        (length: 27, entropy: 4.2 bits/char)
MyC@t'sNameIs$Fluffy#2026      (length: 30, entropy: 4.8 bits/char)
!@#$%^&*()_+ABCDEFGH_12345     (length: 32, entropy: 5.1 bits/char)
```

#### ❌ WEAK passphrases

```
password                          (dictionary word, very weak)
12345678                          (numbers only, low entropy)
mario                             (single name, low entropy)
```

#### Recommendations

1. **Minimum length:** 12 characters (recommended: 20+)
2. **Mixed characters:** uppercase, lowercase, numbers, symbols
3. **No dictionary words:** avoid names, birthdays, common words
4. **Unique per batch:** use a different passphrase for each sensitive batch
5. **Store securely:** use a password manager (1Password, Bitwarden, KeePass)

**The tool automatically validates entropy.** If your passphrase is weak, you will receive a warning.

### What If You Lose Your Passphrase

- ❌ **You cannot decrypt mapping.enc**
- ❌ **Original data remains lost** (pseudonyms stay)
- ✅ But mapping.enc remains encrypted (safe from attacks)

**Store your passphrase in a secure location.** For critical work, use a password manager with encrypted backup.

---

## Complete Example Workflow

Scenario: A company wants to analyze 500 support emails with ChatGPT for sentiment analysis without exposing PII.

### Initial Setup

1. **Upload 500 emails to the Tool**
   - Format: .txt, .csv, .eml
   - Select mode: `STRICT` (detect all PII entities)
   - Preset: `SOC Logs` (fixed — no user selection required)

2. **Scan**
   - Tool detects: 1,250 PII entities (names, emails, IPs, etc.)
   - Generates pseudonyms: EMAIL_001, PERSON_001, IPV4_001, etc.

3. **Review and Apply**
   - Review each entity (optional: customize pseudonyms)
   - Apply → download ZIP containing:
     - `files/` → 500 pseudonymized emails
     - `report.html` → substitution audit trail
     - `mapping.enc` → encrypted mapping

### "Prepare for AI" Phase

4. **Extract a sample email**
   ```
   Subject: Login issue
   From: EMAIL_001
   To: EMAIL_002
   
   "Hi, I'm PERSON_001 and can't login from PERSON_002..."
   ```

5. **Download mapping.enc and passphrase**
   - mapping.enc: `mapping_batch_xyz.enc`
   - Passphrase: `MyC@t'sNameIs$Fluffy#2026`

### "Send to ChatGPT" Phase

6. **Paste pseudonymized email to ChatGPT**
   ```
   Prompt:
   "Analyze the sentiment of this support ticket:
   
   Subject: Login issue
   From: EMAIL_001
   To: EMAIL_002
   
   Hi, I'm PERSON_001 and can't login from PERSON_002..."
   ```

7. **ChatGPT responds:**
   ```
   Sentiment: NEGATIVE (moderate frustration)
   
   Recommended actions:
   - Contact EMAIL_001 to verify credentials
   - Check if PERSON_001 has 2FA enabled
   - Reset password for PERSON_002...
   ```

### "Decrypt AI Response" Phase

8. **In the tool, "Decrypt AI Response" tab:**
   - Upload `mapping_batch_xyz.enc`
   - Enter passphrase: `MyC@t'sNameIs$Fluffy#2026`
   - Paste ChatGPT response
   - Click "Decrypt"

9. **Receive decrypted response:**
   ```
   Sentiment: NEGATIVE (moderate frustration)
   
   Recommended actions:
   - Contact mario.rossi@acme.com to verify credentials
   - Check if Giovanni Rossi has 2FA enabled
   - Reset password for Maria Bianchi...
   ```

✅ **Workflow complete.** You now have:
- Complete AI analysis
- Response with original data restored
- No PII ever sent to ChatGPT

---

## Troubleshooting

### Q: "Passphrase is incorrect for this mapping.enc"

**Problem:** The passphrase you entered doesn't match.

**Solutions:**
1. ✅ Copy passphrase from password manager (don't type manually)
2. ✅ Check if you used correct UPPERCASE/lowercase
3. ✅ Verify you downloaded the correct mapping.enc (matching batch)
4. ❌ If passphrase is lost: you cannot decrypt (use mapping.enc backup)

---

### Q: "File is not a valid mapping.enc (magic header not recognized)"

**Problem:** The downloaded file is not a valid mapping.enc.

**Solutions:**
1. ✅ Verify you downloaded the correct file (should end in `.enc`)
2. ✅ Check that file wasn't corrupted during download/email
3. ✅ If it's an old backup, it might be legacy format v1 (backward compatible)
4. ❌ If file is truly corrupted: download again from the tool

---

### Q: "Text too long"

**Problem:** Text you're decrypting is > 200,000 characters.

**Solutions:**
1. ✅ Split text into smaller sections
2. ✅ Use "Revert Batch" for large files (supports up to 50 MB)
3. ✅ Contact admin to increase limit (configurable)

---

### Q: "Preview shows 0 matches"

**Problem:** The tool found no pseudonyms in the text.

**Solutions:**
1. ✅ Verify you pasted text from AI response (not original)
2. ✅ Check that mapping.enc and text belong to same batch
3. ✅ If AI modified pseudonyms (e.g., "EMAIL_001" → "email_001"), they won't match (case-sensitive)

---

### Q: "How can I customize a pseudonym before sending to AI?"

**Solution:**
During the "Review" phase (before Apply), click each finding and customize it.
Example: `EMAIL_001` → `USER_A` (more readable for AI).

Then continue to "Prepare for AI" (customized pseudonyms go into mapping.enc).

---

## Related Links

- [README.md](../README.md) — Installation and setup
- [docs/06_Detector_Strategy.md](../docs/06_Detector_Strategy.md) — How the Tool detects PII entities
- [docs/04_Policies.md](../docs/04_Policies.md) — What each policy detects
- [docs/13_Super_Critical_Analysis.md](../docs/13_Super_Critical_Analysis.md) — Project analysis and roadmap

---

**Last updated:** March 2026  
**Tool version:** v5.0.0  
**Contact:** Team for document improvements
