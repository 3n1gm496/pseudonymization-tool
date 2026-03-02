#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Local Pseudonymization Tool — Preparazione Pacchetto Offline (Linux/macOS)
#
# UTILIZZO:
#   Eseguire su una macchina CON accesso internet.
#   Verrà creata la cartella "wheelhouse/" con tutti i wheel precompilati.
#   Copiare l'intera cartella del tool (incluso wheelhouse/) sulla macchina
#   target senza internet e avviare start.sh normalmente.
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
WHEELHOUSE_DIR="$SCRIPT_DIR/wheelhouse"

echo ""
echo "  +------------------------------------------------------+"
echo "  |  Preparazione Pacchetto Offline                     |"
echo "  |  Local Pseudonymization Tool -- MVP v1.0.0          |"
echo "  +------------------------------------------------------+"
echo ""

# Trova Python 3.10-3.12
PYTHON_CMD=""
for py in python3.11 python3.12 python3.10 python3 python; do
    if command -v "$py" &>/dev/null; then
        if "$py" -c "import sys; v=sys.version_info; exit(0 if (3,10)<=v<(3,13) else 1)" 2>/dev/null; then
            PYTHON_CMD="$py"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERR]  Python 3.10/3.11/3.12 non trovato."
    exit 1
fi

PY_VER=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
echo "[INFO] Python $PY_VER trovato."
echo "[INFO] Download wheel in: $WHEELHOUSE_DIR"
echo "[INFO] Connessione internet richiesta..."
echo ""

mkdir -p "$WHEELHOUSE_DIR"

"$PYTHON_CMD" -m pip download \
    --dest "$WHEELHOUSE_DIR" \
    -r "$BACKEND_DIR/requirements.txt"

echo ""
echo "[OK]   Wheel scaricati in: $WHEELHOUSE_DIR"
echo ""
echo "  PROSSIMI PASSI:"
echo "  1. Copiare l'intera cartella del tool sulla macchina target"
echo "     (incluso wheelhouse/)"
echo "  2. Sulla macchina target: ./start.sh"
echo "     (rileva automaticamente wheelhouse/)"
echo ""
