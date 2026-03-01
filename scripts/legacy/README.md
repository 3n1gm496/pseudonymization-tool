# Legacy Scripts — Non-Docker Installation

⚠️ **These scripts are for systems WITHOUT Docker support.**

**When to use:**
- Air-gapped/offline environments (no internet access)
- Windows/Linux systems without Docker installed
- Corporate environments where Docker is restricted

**Recommended method for most users:**
Use Docker instead → `make start` (see main README.md)

---

## Quick Start (Linux/macOS)

```bash
./start.sh
```

## Quick Start (Windows)

Double-click `start.bat` or run in PowerShell:
```powershell
.\start.bat
```

---

## Offline Installation

### Step 1: Prepare (on internet-connected machine)

```bash
./prepare_offline.sh   # Linux/macOS
./prepare_offline.bat  # Windows
```

This creates a `wheelhouse/` folder with all dependencies.

### Step 2: Transfer

Copy the **entire tool folder** (including `wheelhouse/`) to the target machine.

### Step 3: Run (on air-gapped machine)

```bash
./start.sh   # Will auto-detect wheelhouse/ and install offline
```

---

## Requirements

- **Python 3.11** (recommended) or 3.10-3.12
- **Tesseract OCR** (optional, for image processing)

---

## Troubleshooting

**Python not found:**
- Install Python 3.11 from https://www.python.org/downloads/

**Tesseract not found (Linux):**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-ita
```

**Tesseract not found (Windows):**
- Download from https://github.com/UB-Mannheim/tesseract/wiki

---

## Notes

- First run downloads ~100MB of Python packages (requires internet)
- Subsequent runs are 100% offline
- Environment is created in `.venv/` folder
- Frontend is served from `frontend/dist/` (pre-built)
