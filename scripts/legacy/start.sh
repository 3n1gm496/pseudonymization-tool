#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Local Pseudonymization Tool — Script di Avvio (Linux/macOS)
# Versione: 1.0.3
# Target Python: 3.11 (testato e supportato)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
VENV_DIR="$REPO_ROOT/.venv"
WHEELHOUSE_DIR="$SCRIPT_DIR/wheelhouse"
LOG_FILE="$SCRIPT_DIR/install.log"
HOST="127.0.0.1"
PORT="8000"

# ─── Colori ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERR]${NC}  $*"; }

# ─── Banner ──────────────────────────────────────────────────────────────────
echo ""
echo "  +------------------------------------------------------+"
echo "  |       Local Pseudonymization Tool -- MVP v1.0.0     |"
echo "  |  Solo uso locale -- Nessun dato inviato all'esterno  |"
echo "  +------------------------------------------------------+"
echo ""

# ─── Verifica Python ─────────────────────────────────────────────────────────
log_info "Verifica Python..."

PYTHON_CMD=""
for cmd in python3.11 python3.12 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; v=sys.version_info; exit(0 if (3,10)<=v<(3,13) else 1)" 2>/dev/null; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    log_error "Python 3.10, 3.11 o 3.12 non trovato."
    echo ""
    echo "  Questo tool è testato con Python 3.11 (raccomandato)."
    echo "  Python 3.13+ non è ancora supportato."
    echo "  Installare Python 3.11 da: https://www.python.org/downloads/release/python-3119/"
    echo ""
    exit 1
fi

PY_VER=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
log_ok "Python $PY_VER trovato ($PYTHON_CMD)."

# Avvisa se non è 3.11
if ! "$PYTHON_CMD" -c "import sys; exit(0 if sys.version_info[:2]==(3,11) else 1)" 2>/dev/null; then
    log_warn "Versione consigliata: Python 3.11. La versione $PY_VER potrebbe funzionare ma non è stata testata."
fi

# ─── Verifica Tesseract OCR ───────────────────────────────────────────────────
log_info "Verifica Tesseract OCR..."
if command -v tesseract &>/dev/null; then
    TESS_VER=$(tesseract --version 2>&1 | head -1)
    log_ok "Tesseract trovato: $TESS_VER"
    if tesseract --list-langs 2>&1 | grep -q "ita"; then
        log_ok "Language pack italiano disponibile."
    else
        log_warn "Language pack italiano non trovato. OCR funzionerà solo in inglese."
        log_warn "Installare con: sudo apt-get install tesseract-ocr-ita"
    fi
else
    log_warn "Tesseract OCR non trovato. L'OCR su immagini non sarà disponibile."
    log_warn "Installare con: sudo apt-get install tesseract-ocr tesseract-ocr-ita"
fi

# ─── Ambiente Virtuale ────────────────────────────────────────────────────────
log_info "Configurazione ambiente virtuale..."

if [ ! -d "$VENV_DIR" ]; then
    log_info "Creazione ambiente virtuale in $VENV_DIR..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    log_ok "Ambiente virtuale creato."
fi

source "$VENV_DIR/bin/activate"
PYTHON_CMD="$VENV_DIR/bin/python"
PIP_CMD="$VENV_DIR/bin/pip"

# ─── Installazione Dipendenze ─────────────────────────────────────────────────
log_info "Verifica dipendenze Python..."

REQUIREMENTS_FILE="$BACKEND_DIR/requirements.txt"
INSTALLED_MARKER="$VENV_DIR/.deps_installed"

if [ ! -f "$INSTALLED_MARKER" ] || [ "$REQUIREMENTS_FILE" -nt "$INSTALLED_MARKER" ]; then
    log_info "Installazione dipendenze... (log: $LOG_FILE)"

    {
        echo "=== $(date) ==="
        echo "Python: $PY_VER"
        echo "Requirements: $REQUIREMENTS_FILE"
        echo ""
    } > "$LOG_FILE"

    # Step 1: aggiorna pip, setuptools, wheel
    log_info "Aggiornamento pip, setuptools, wheel..."
    "$PIP_CMD" install --upgrade pip setuptools wheel >> "$LOG_FILE" 2>&1 || \
        log_warn "Aggiornamento pip/setuptools/wheel fallito (non critico)."

    # Step 2: installa dipendenze (offline se wheelhouse/ presente, online altrimenti)
    if [ -d "$WHEELHOUSE_DIR" ] && [ "$(ls -A "$WHEELHOUSE_DIR" 2>/dev/null)" ]; then
        log_info "Modalità OFFLINE: uso wheelhouse/ locale."
        "$PIP_CMD" install \
            --no-index \
            --find-links "$WHEELHOUSE_DIR" \
            -r "$REQUIREMENTS_FILE" >> "$LOG_FILE" 2>&1
    else
        log_info "Modalità ONLINE: download da PyPI..."
        "$PIP_CMD" install -r "$REQUIREMENTS_FILE" >> "$LOG_FILE" 2>&1
    fi

    PIP_EXIT=$?
    echo "" >> "$LOG_FILE"
    echo "=== Fine installazione. Exit code: $PIP_EXIT ===" >> "$LOG_FILE"

    if [ $PIP_EXIT -ne 0 ]; then
        log_error "Installazione dipendenze fallita."
        echo ""
        echo "  Ultime righe del log ($LOG_FILE):"
        echo "  ─────────────────────────────────────────────────────"
        tail -60 "$LOG_FILE" | sed 's/^/  /'
        echo "  ─────────────────────────────────────────────────────"
        echo ""
        exit 1
    fi

    touch "$INSTALLED_MARKER"
    log_ok "Dipendenze installate. Log: $LOG_FILE"
else
    log_ok "Dipendenze già installate."
fi

# ─── Avvio Server ─────────────────────────────────────────────────────────────
log_info "Avvio del server su http://$HOST:$PORT ..."
echo ""
echo "  +------------------------------------------------------+"
echo "  |  Apri il browser su: http://localhost:$PORT           |"
echo "  |  Premi Ctrl+C per fermare il server                  |"
echo "  +------------------------------------------------------+"
echo ""

# Apri il browser automaticamente (se disponibile)
(sleep 2 && {
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:$PORT" &>/dev/null
    elif command -v open &>/dev/null; then
        open "http://localhost:$PORT" &>/dev/null
    fi
}) &

# Avvia uvicorn
cd "$BACKEND_DIR"
exec "$PYTHON_CMD" -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    --no-access-log
