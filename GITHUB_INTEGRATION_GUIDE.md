# 🐙 INTEGRAZIONE GITHUB — GUIDA COMPLETA

## 📌 INDICE
1. [Setup Iniziale](#setup-iniziale)
2. [Creazione Repository su GitHub](#creazione-repository-su-github)
3. [Autenticazione (SSH vs Token)](#autenticazione-ssh-vs-token)
4. [Push Iniziale](#push-iniziale)
5. [GitHub Actions CI/CD](#github-actions-cicd)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Setup Iniziale

### Prerequisiti
```bash
# Verifica che Git sia installato
git --version

# Configura Git (globale, una volta sola)
git config --global user.name "Tuo Nome"
git config --global user.email "tua.email@example.com"

# Verifica configurazione
git config --global --list
```

### Repository Locali Status
```bash
# Pseudonymization Tool
cd /home/administrator/tools/pseudonymization-tool
git status
git log --oneline -5

# Security Scanning Platform
cd /home/administrator/tools/security-scanning-platform
git status
git log --oneline -5
```

✅ **Stato attuale**: Entrambi i repository sono inizializzati con commit iniziale.

---

## Creazione Repository su GitHub

### 1️⃣ Crea Account GitHub (se non hai)
- Vai a https://github.com/signup
- Compila il modulo e verifica email
- Configura profilo (foto, bio)

### 2️⃣ Crea i Due Repository

#### Repository 1: Pseudonymization Tool
```
Vai a: https://github.com/new

Nome repository:        pseudonymization-tool
Descrizione:            Local tool for securely pseudonymizing sensitive documents
Visibilità:             Public or Private (scelta tua)
Add .gitignore:         ❌ (già fatto)
Add license:            ✅ Scegli una licenza (consiglio: MIT, Apache 2.0, o GPL)
Add README:             ❌ (già fatto)
```

#### Repository 2: Security Scanning Platform
```
Vai a: https://github.com/new

Nome repository:        security-scanning-platform
Descrizione:            Multi-scanner security scanning orchestrator & dashboard
Visibilità:             Public or Private
Add .gitignore:         ❌
Add license:            ✅
Add README:             ❌
```

**Copia gli URL, ti serviranno nel prossimo passo:**
- `https://github.com/TUO_USERNAME/pseudonymization-tool.git`
- `https://github.com/TUO_USERNAME/security-scanning-platform.git`

---

## Autenticazione: SSH vs Token

### Opzione A: SSH (Consigliato) ⭐

#### 1. Genera chiave SSH
```bash
ssh-keygen -t ed25519 -C "tua.email@example.com"
# Oppure (se ed25519 non supportato):
ssh-keygen -t rsa -b 4096 -C "tua.email@example.com"

# Pressiona Enter quando chiede dove salvarla (default ~/.ssh/id_ed25519)
# Inserisci una passphrase (sicura!)
```

#### 2. Aggiungi chiave a ssh-agent
```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

#### 3. Copia chiave pubblica a GitHub
```bash
# Copia la chiave pubblica
cat ~/.ssh/id_ed25519.pub

# Vai a: https://github.com/settings/keys
# Click "New SSH key"
# Titolo:   "Development Machine" (o come preferisci)
# Chiave:   Incolla il contenuto di id_ed25519.pub
# Click "Add SSH key"
```

#### 4. Verifica connessione
```bash
ssh -T git@github.com
# Output atteso: "Hi username! You've successfully authenticated..."
```

### Opzione B: Personal Access Token (PAT)

Se SSH non funziona, usa token:

#### 1. Crea token su GitHub
```
Vai a: https://github.com/settings/tokens

Click "Generate new token" → "Generate new token (classic)"
Note:               "Development Machine"
Expiration:         90 days (o scegli)
Select scopes:      ✅ repo (accesso completo)
                    ✅ workflow (GitHub Actions)
                    ✅ gist
Click "Generate token"
```

#### 2. Salva il token (monouso!)
```bash
# Copia il token mostrato (unica volta!)
# NON condividerlo MAI

# Salvalo localmente (meglio in password manager)
# Es. 1Password, Bitwarden, LastPass, etc.
```

#### 3. Se usi token con HTTPS
```bash
# Git chiederà username (TUO_USERNAME) e password (TOKEN)
# Oppure configura credenziali:

git config --global credential.helper store
# Attenzione: salva le credenziali in chiaro! Usa con cautela.

# Meglio: usa SSH o token con credential.helper cache
git config --global credential.helper cache
```

---

## Push Iniziale

### Con SSH (consigliato)
```bash
# Pseudonymization Tool
cd /home/administrator/tools/pseudonymization-tool
git remote add origin git@github.com:TUO_USERNAME/pseudonymization-tool.git
git branch -M main
git push -u origin main

# Security Scanning Platform
cd /home/administrator/tools/security-scanning-platform
git remote add origin git@github.com:TUO_USERNAME/security-scanning-platform.git
git branch -M main
git push -u origin main
```

### Con HTTPS + Token
```bash
# Pseudonymization Tool
cd /home/administrator/tools/pseudonymization-tool
git remote add origin https://github.com/TUO_USERNAME/pseudonymization-tool.git
git branch -M main
git push -u origin main
# Username: TUO_USERNAME
# Password: TOKEN

# Security Scanning Platform
cd /home/administrator/tools/security-scanning-platform
git remote add origin https://github.com/TUO_USERNAME/security-scanning-platform.git
git branch -M main
git push -u origin main
```

### Verifica Push
```bash
cd /home/administrator/tools/pseudonymization-tool
git remote -v
# Deve mostrare origin URL

# Verifica che il repository è visibile su GitHub
# https://github.com/TUO_USERNAME/pseudonymization-tool
```

---

## GitHub Actions CI/CD

### Setup: Test Automatici

Crea file `.github/workflows/tests.yml` per Pseudonymization Tool:

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r backend/requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        cd backend
        pytest tests/ -v --cov=app --cov-report=xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./backend/coverage.xml
        fail_ci_if_error: true
```

Crea file `.github/workflows/tests.yml` per Security Scanning Platform:

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]

    services:
      sqlite:
        image: sqlite:latest

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r orchestrator/requirements.txt
        pip install pytest pytest-cov
        pip install -r dashboard/requirements.txt
    
    - name: Run orchestrator tests
      run: |
        cd orchestrator
        pytest tests/ -v --cov=. --cov-report=xml
    
    - name: Run dashboard tests
      run: |
        cd dashboard
        pytest tests/ -v --cov=. --cov-report=xml
```

### Setup: Linting & Type Checking

Crea file `.github/workflows/lint.yml`:

```yaml
name: Lint & Type Check

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  lint:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install linting tools
      run: |
        python -m pip install --upgrade pip
        pip install black flake8 mypy isort
    
    - name: Format check with Black
      run: black --check .
    
    - name: Lint with Flake8
      run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
    
    - name: Type check with Mypy
      run: mypy . --ignore-missing-imports || true
    
    - name: Sort imports with isort
      run: isort --check-only .
```

---

## Best Practices

### 1. Branching Strategy (Git Flow)

```bash
# main:    produzione (versioni stabili)
# develop: sviluppo (integrazione features)
# feature/*: nuove features
# bugfix/*:  correzioni bugs
# release/*: preparazione release

# Creare una feature
git checkout -b feature/new-detector
# ...fai modifiche...
git add .
git commit -m "feat: add new PII detector"
git push origin feature/new-detector
# Crea Pull Request su GitHub

# Merge via PR (con code review)
```

### 2. Commit Messages (Conventional Commits)

```
feat:     Nuova feature
fix:      Correzione bug
docs:     Documentazione
style:    Formattazione, senza logica
refactor: Refactoring codice
perf:     Miglioramenti performance
test:     Test aggiunti/modificati
chore:    Dependency updates, build
```

**Esempi:**
```git
feat: add email pseudonymization detector
fix: resolve memory leak in parse_results cache
docs: update README with GitHub setup
refactor: extract common error handling logic
test: add unit tests for crypto module
perf: implement regex compilation caching
```

### 3. .github/CONTRIBUTING.md

```markdown
# Contributing

## Come iniziare
1. Fork il repository
2. Crea branch feature: `git checkout -b feature/my-feature`
3. Commit: `git commit -am 'feat: add my feature'`
4. Push: `git push origin feature/my-feature`
5. Crea Pull Request

## Code Standards
- Python 3.11+
- Type hints obbligatori
- Test coverage > 80%
- Black formatting
- No secrets in commits
```

### 4. Pull Request Template (.github/pull_request_template.md)

```markdown
## Descrizione
Breve descrizione dei cambiamenti

## Tipo di Cambio
- [ ] Bug fix
- [ ] Nuova feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests scritti
- [ ] Test coverage >= 80%
- [ ] Manualmente testato

## Checklist
- [ ] Code segue style guidelines
- [ ] No secrets o credenziali
- [ ] Documentazione aggiornata
```

---

## Troubleshooting

### ❌ "Permission denied (publickey)"
```bash
# SSH key non configurato
ssh-keygen -t ed25519 -C "tua.email@example.com"
ssh-add ~/.ssh/id_ed25519

# Verifica:
ssh -T git@github.com
```

### ❌ "fatal: remote origin already exists"
```bash
git remote remove origin
git remote add origin git@github.com:TUO_USERNAME/pseudonymization-tool.git
```

### ❌ "fatal: 'origin' does not appear to be a 'git' repository"
```bash
# Verifica che sei nella directory giusta
pwd
git remote -v

# Se vuoto, aggiungi remote:
git remote add origin git@github.com:TUO_USERNAME/nome-repo.git
```

### ❌ Token scaduto
```bash
# Ricrea token su https://github.com/settings/tokens
# Update locale:
git remote set-url origin https://NUOVO_TOKEN@github.com/username/repo.git
```

### ❌ .gitignore non funziona
```bash
# Le file già trackate non saranno ignorate!
# Soluzione:
git rm -r --cached .
git add .
git commit -m "fix: respect .gitignore"
```

---

## Prossimi Passi

1. ✅ **Aggiungere protections** su branch main:
   - Vai a Settings → Branches
   - Abilita "Require pull request reviews"
   - Abilita "Require status checks to pass"

2. ✅ **Configurare Codecov** per coverage tracking:
   - https://codecov.io
   - Sync repository GitHub
   - Badge nel README

3. ✅ **Aggiungere Issues & Discussions**:
   - Template per bug reports
   - Template per feature requests
   - Discussions per Q&A

4. ✅ **Setup Releases**:
   - Semantic Versioning (v1.0.0)
   - Changelog automatico
   - Release notes

---

**Hai domande? Consulta la [Documentazione GitHub](https://docs.github.com)**
