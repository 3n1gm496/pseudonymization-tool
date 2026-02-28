# 🔐 Pseudonymization Tool — GitHub Integration

## Quick Start (5 minuti)

### 1. Prepara SSH Key (una volta sola)
```bash
# Genera chiave SSH
ssh-keygen -t ed25519 -C "tua.email@example.com"

# Aggiungi a ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Copia chiave pubblica a GitHub
# https://github.com/settings/keys → "New SSH key"
cat ~/.ssh/id_ed25519.pub
```

### 2. Setup Repository
```bash
cd /home/administrator/tools
./github-setup.sh TUO_USERNAME_GITHUB
```

### 3. Crea Repository su GitHub
- Vai a https://github.com/new
- **Nome**: `pseudonymization-tool`
- **Descrizione**: Local tool for securely pseudonymizing sensitive documents
- **Visibilità**: Public (consigliato per open source)
- Copia il repository URL SSH

### 4. Push Iniziale
```bash
cd /home/administrator/tools/pseudonymization-tool

# Verifica remote
git remote -v

# Push
git push -u origin main
```

### 5. (Opzionale) GitHub Actions
```bash
# Configura workflows automatici
cd /home/administrator/tools
./setup-github-actions.sh

cd pseudonymization-tool
git add .github/
git commit -m "chore: add GitHub Actions workflows"
git push origin main
```

---

## Repository Structure
```
pseudonymization-tool/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/            # REST endpoints
│   │   ├── core/           # Business logic
│   │   ├── detectors/      # PII detection engine
│   │   ├── parsers/        # Document parsers
│   │   ├── pseudonymizer/  # Pseudonymization logic
│   │   └── models/         # Pydantic schemas
│   ├── tests/              # Test suite
│   └── requirements.txt     # Dependencies
├── frontend/                # Web UI (HTML/CSS/JS)
├── docs/                    # Documentation
├── .github/workflows/       # CI/CD workflows
└── README.md
```

---

## Development Workflow

### Creare una Feature
```bash
# Da main
git checkout -b feature/my-feature

# Fai modifiche, test
pytest backend/tests/

# Commit (conventional commits)
git add .
git commit -m "feat: add new PII detector 

- Description of changes
- Technical details if needed"

# Push
git push origin feature/my-feature

# Crea Pull Request su GitHub
# Descrizione, screenshot, test coverage info
```

### Format e Lint
```bash
# Installa dev tools
pip install black flake8 mypy pytest pytest-cov

# Format with Black
black backend/

# Lint
flake8 backend/app backend/tests

# Type check
mypy backend/app

# Test
pytest backend/tests/ -v --cov=app
```

---

## Protections su Main Branch

Vai a: **Repository Settings → Branches → Branch protection rules**

Configura per `main`:
- [x] Require a pull request before merging
- [x] Require approvals (1 review)
- [x] Require status checks to pass
  - tests
  - lint
- [x] Require branches to be up to date
- [x] Include administrators

---

## Releases & Versioning

Usa **Semantic Versioning**: `vMAJOR.MINOR.PATCH`

```bash
# Testa tutto
pytest backend/tests/ -v

# Tag release
git tag -a v1.0.0 -m "Release v1.0.0: MVP with core features"

# Push tag
git push origin v1.0.0

# Nota: GitHub crea automaticamente "Releases" dai tags
# Aggiungi release notes via GitHub UI
```

---

## Troubleshooting

### "fatal: 'origin' does not appear to be a 'git' repository"
```bash
git remote add origin git@github.com:TUO_USERNAME/pseudonymization-tool.git
```

### "Permission denied (publickey)"
```bash
# Riconfigura SSH
ssh-keygen -t ed25519
ssh-add ~/.ssh/id_ed25519

# Verifica
ssh -T git@github.com
```

### Merge conflicts durante PR
```bash
git fetch origin
git rebase origin/main
# Risolvi conflitti in editor
git add .
git rebase --continue
git push origin feature/my-feature --force
```

---

## Risorse Utili
- [GitHub Docs](https://docs.github.com)
- [Conventional Commits](https://www.conventionalcommits.org)
- [Semantic Versioning](https://semver.org)
- [FastAPI Docs](https://fastapi.tiangolo.com)
- [Python Testing Best Practices](https://docs.pytest.org)
