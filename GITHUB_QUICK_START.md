# 🚀 GITHUB INTEGRATION — QUICK REFERENCE CHECKLIST

Stampa questo documento e seguilo step by step.

---

## ✅ FASE 1: SETUP LOCALE (fatto ✓)

- [x] Repository Git inizializzati
- [x] .gitignore configurati
- [x] Primo commit effettuato

**Verifica stato:**
```bash
cd /home/administrator/tools/pseudonymization-tool
git log --oneline -1
# Output: e3fd5c8 (HEAD -> master) Initial commit: Pseudonymization Tool MVP

cd /home/administrator/tools/security-scanning-platform
git log --oneline -1
# Output: f0128a3 (HEAD -> master) Initial commit: Security Scanning Platform
```

---

## ✅ FASE 2: SETUP SSH (5 minuti)

### Step 1: Genera chiave SSH
```bash
ssh-keygen -t ed25519 -C "tua.email@example.com"
# Pressiona Enter per il percorso default (~/.ssh/id_ed25519)
# Inserisci una passphrase (importante!)
```

### Step 2: Aggiungi a ssh-agent
```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### Step 3: Copia chiave pubblica
```bash
cat ~/.ssh/id_ed25519.pub
# Copia l'output (inizia con "ssh-ed25519 ...")
```

### Step 4: Aggiungi a GitHub
1. Vai a: https://github.com/settings/keys
2. Click "New SSH key"
3. Titolo: "Development Machine"
4. Incolla la chiave pubblica
5. Click "Add SSH key"

### Step 5: Verifica connessione
```bash
ssh -T git@github.com
# Output atteso: "Hi username! You've successfully authenticated..."
```

---

## ✅ FASE 3: CREARE REPOSITORY SU GITHUB (3 minuti)

### Repository 1: Pseudonymization Tool
1. Vai a: https://github.com/new
2. **Repository name**: `pseudonymization-tool`
3. **Description**: Local tool for securely pseudonymizing sensitive documents
4. **Visibility**: Public ⭐ (per attirare collaboratori)
5. **Add .gitignore**: No (già fatto)
6. **Add license**: Choose a license
7. Click "Create repository"
8. **Copia URL**: `git@github.com:TUO_USERNAME/pseudonymization-tool.git`

### Repository 2: Security Scanning Platform
1. Vai a: https://github.com/new
2. **Repository name**: `security-scanning-platform`
3. **Description**: Multi-scanner security orchestrator with normalized reporting
4. **Visibility**: Public ⭐
5. **Add .gitignore**: No
6. **Add license**: Choose a license
7. Click "Create repository"
8. **Copia URL**: `git@github.com:TUO_USERNAME/security-scanning-platform.git`

---

## ✅ FASE 4: CONNETTERE REPOSITORY LOCALI A GITHUB (5 minuti)

### Opzione A: Script Automatico (Consigliato)

```bash
cd /home/administrator/tools
./github-setup.sh TUO_USERNAME_GITHUB

# Follows:
# 1. Configura Git globale
# 2. Aggiungi remote a entrambi i repository
# 3. Rinomina branch master → main
```

### Opzione B: Comandi Manuali

**Pseudonymization Tool:**
```bash
cd /home/administrator/tools/pseudonymization-tool

# Aggiungi remote
git remote add origin git@github.com:TUO_USERNAME/pseudonymization-tool.git

# Rinomina branch
git branch -m master main

# Verifica
git remote -v
git branch
```

**Security Scanning Platform:**
```bash
cd /home/administrator/tools/security-scanning-platform

git remote add origin git@github.com:TUO_USERNAME/security-scanning-platform.git
git branch -m master main

git remote -v
git branch
```

---

## ✅ FASE 5: PUSH INIZIALE (2 minuti)

### Pseudonymization Tool
```bash
cd /home/administrator/tools/pseudonymization-tool
git push -u origin main
# Inserisci passphrase SSH se richiesto
```

### Security Scanning Platform
```bash
cd /home/administrator/tools/security-scanning-platform
git push -u origin main
# Inserisci passphrase SSH se richiesto
```

### Verifica
Visita i tuoi repository su GitHub:
- https://github.com/TUO_USERNAME/pseudonymization-tool
- https://github.com/TUO_USERNAME/security-scanning-platform

Dovresti vedere tutti i file!

---

## ✅ FASE 6: CONFIGURARE GITHUB ACTIONS (3 minuti)

### Setup Automatico

```bash
cd /home/administrator/tools
./setup-github-actions.sh

# Successivamente:
cd pseudonymization-tool
git add .github/
git commit -m "chore: add GitHub Actions workflows"
git push origin main

cd ../security-scanning-platform
git add .github/
git commit -m "chore: add GitHub Actions workflows"
git push origin main
```

### Verifica
Visita i repository e guarda la sezione "Actions":
- Dovrebbero eseguire automaticamente su ogni push
- Controlla i test & linting

---

## ✅ FASE 7: CONFIGURARE BRANCH PROTECTION (Opzionale ma Consigliato)

Per ogni repository:

1. Vai a **Settings → Branches**
2. Click "Add rule"
3. **Branch name pattern**: `main`
4. Configura:
   - [x] Require a pull request before merging
   - [x] Require approvals (1 review)
   - [x] Require status checks to pass
   - [x] Include administrators
5. Click "Create"

**Benefici:**
- ✅ Nessuno può pushare direttamente su main
- ✅ Tutti i PR devono passare i test
- ✅ Revisione del codice obbligatoria

---

## 📝 WORKFLOW QUOTIDIANO

### Per una nuova feature:

```bash
# Crea feature branch
git checkout -b feature/new-feature

# Fai modifiche, test
# ...

# Commit (conventional commits)
git add .
git commit -m "feat: add new feature description"

# Push
git push origin feature/new-feature

# Crea Pull Request su GitHub
# (o usa: gh pr create)

# Aspetta approvazione CI/CD + code review
# Merge via GitHub UI
```

### Update locale da GitHub:

```bash
git fetch origin
git pull origin main
```

### Sincronizza fork (se hai fatto fork di qualcosa):

```bash
git remote add upstream https://github.com/ORIGINAL_OWNER/REPO.git
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

---

## 🎯 PROSSIMI STEP CONSIGLIATI

### Immediato (dopo push):
- [ ] Aggiungi collaboratori (Settings → Collaborators)
- [ ] Configura branch protection su main
- [ ] Abilita Discussions (Settings → Options)

### Corto termine (1-2 settimane):
- [ ] Configura Codecov per coverage tracking
- [ ] Aggiungi badges al README (build status, coverage)
- [ ] Setup semantic release automation
- [ ] Crea issue templates per bug/features

### Lungo termine:
- [ ] Imposta Milestones per releases
- [ ] Crea progetto board (GitHub Projects)
- [ ] Setup pre-commit hooks locali
- [ ] Considera CODEOWNERS file

---

## 🆘 TROUBLESHOOTING RAPIDO

| Problema | Soluzione |
|----------|-----------|
| "Permission denied (publickey)" | `ssh-add ~/.ssh/id_ed25519` |
| "fatal: remote origin already exists" | `git remote remove origin` |
| "fatal: 'origin' does not appear to be a 'git' repository" | `git remote add origin ...` |
| Non riesco a fare push | Verifica SSH: `ssh -T git@github.com` |
| Accidentalmente pushato file sensibile | `git rm --cached file` + nuovo commit |
| Voglio cancellare il repository remotom | Settings → Danger Zone → Delete |

---

## 📚 COMANDI UTILI DA RICORDARE

```bash
# Verificare stato
git status
git log --oneline -10
git remote -v

# Sincronizzare
git fetch origin
git pull origin main
git push origin main

# Branching
git branch
git checkout -b feature/name
git branch -d feature/name

# Committing
git add .
git commit -m "feat: description"
git commit --amend  # Modifica ultimo commit

# Undo
git revert COMMIT_HASH  # Crea nuovo commit che annulla
git reset HEAD~1        # Annulla ultimo commit (attento!)

# Stashing
git stash     # Salva work in progress
git stash pop # Riprendi work in progress
```

---

## 🎉 COMPLETATO!

Se hai finito tutti i step della checklist, hai:
- ✅ Repository Git inizializzati localmente
- ✅ SSH configurato
- ✅ Repository creati su GitHub
- ✅ Push iniziale completato
- ✅ GitHub Actions configured (opzionale)
- ✅ Pronto per il development collaborativo!

**Domande?** Consulta:
- Guida principale: `/home/administrator/tools/GITHUB_INTEGRATION_GUIDE.md`
- Guide specifiche:
  - Pseudonymization: `pseudonymization-tool/.github/README.md`
  - Security Scanning: `security-scanning-platform/.github/README.md`
