"""
Configurazione centrale dell'applicazione.
"""
import os
import tempfile
from pathlib import Path

# Directory base del backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Directory per i file temporanei dei batch
TEMP_BASE_DIR = Path(tempfile.gettempdir()) / "pseudonymizer_batches"
TEMP_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Directory di configurazione (dizionari, pattern custom)
CONFIG_DIR = BASE_DIR / "config"
DICTIONARIES_DIR = CONFIG_DIR / "dictionaries"

# Porta del server
SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.environ.get("PSEUDONYMIZER_PORT", "8000"))

# Formati di file supportati
SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf", ".xlsx", ".jpg", ".jpeg", ".png"}

# Lingue OCR
OCR_LANGUAGES = "ita+eng"

# Dimensione massima upload (50 MB per file)
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Rate limiting API (best-effort in-memory)
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
