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

# Directory runtime per stato applicativo scrivibile (non in config read-only)
STATE_DIR = Path(os.environ.get("PSEUDONYMIZER_STATE_DIR", str(TEMP_BASE_DIR / "state")))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "state.json"

# Directory di configurazione (dizionari, pattern custom)
CONFIG_DIR = BASE_DIR / "config"
DICTIONARIES_DIR = CONFIG_DIR / "dictionaries"

# Indirizzo di bind del server.
# Default: 127.0.0.1 (sicuro per sviluppo locale).
# In Docker/produzione impostare PSEUDONYMIZER_HOST=0.0.0.0 per rendere
# il container raggiungibile dall'esterno.
SERVER_HOST = os.environ.get("PSEUDONYMIZER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("PSEUDONYMIZER_PORT", "8000"))

# Formati di file supportati
SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".docx", ".pdf", ".xlsx", ".jpg", ".jpeg", ".png"}


def validate_writable_paths() -> None:
    """
    ✅ FIX #I-005: Validate that STATE_DIR is writable.
    Fails early if running in environment with read-only filesystem (e.g., misconfigured Docker).
    
    Raises RuntimeError if paths are not writable.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Test STATE_DIR writability
    test_file = STATE_DIR / ".writable_test"
    try:
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        logger.info("✅ STATE_DIR writable: %s", STATE_DIR)
    except (OSError, IOError, PermissionError) as e:
        raise RuntimeError(
            f"❌ STATE_DIR is not writable: {STATE_DIR}\n"
            f"   This path must be mounted as read-write in Docker/K8s configs.\n"
            f"   Error: {e}"
        ) from e


# Lingue OCR
OCR_LANGUAGES = "ita+eng"

# Dimensione massima upload (50 MB per file)
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Rate limiting API (best-effort in-memory)
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Scan queue / concurrency controls
MAX_CONCURRENT_SCANS = int(os.environ.get("MAX_CONCURRENT_SCANS", "2"))

# Parallel file processing per batch
PARALLEL_FILE_PROCESSING = os.environ.get("PARALLEL_FILE_PROCESSING", "true").lower() == "true"
MAX_PARALLEL_FILES = int(os.environ.get("MAX_PARALLEL_FILES", "4"))

# Streaming per file grandi
STREAMING_THRESHOLD_MB = int(os.environ.get("STREAMING_THRESHOLD_MB", "50"))
STREAMING_CHUNK_SIZE = int(os.environ.get("STREAMING_CHUNK_SIZE", "1000"))

# Caching detector results
DETECTOR_CACHE_ENABLED = os.environ.get("DETECTOR_CACHE_ENABLED", "true").lower() == "true"
DETECTOR_CACHE_TTL_SECONDS = int(os.environ.get("DETECTOR_CACHE_TTL_SECONDS", "3600"))
DETECTOR_CACHE_MAX_SIZE = int(os.environ.get("DETECTOR_CACHE_MAX_SIZE", "10000"))

# ML/NER detector
ML_NER_ENABLED = os.environ.get("ML_NER_ENABLED", "true").lower() == "true"
ML_NER_MODEL = os.environ.get("ML_NER_MODEL", "en_core_web_sm")
ML_NER_CONFIDENCE_THRESHOLD = float(os.environ.get("ML_NER_CONFIDENCE_THRESHOLD", "0.7"))

# Batch TTL and cleanup
BATCH_INACTIVITY_TTL_HOURS = int(os.environ.get("BATCH_INACTIVITY_TTL_HOURS", "24"))
BATCH_CLEANUP_INTERVAL_SECONDS = int(os.environ.get("BATCH_CLEANUP_INTERVAL_SECONDS", "3600"))

# File processing timeouts
FILE_PROCESSING_TIMEOUT_SECONDS = int(os.environ.get("FILE_PROCESSING_TIMEOUT_SECONDS", "300"))
API_HEAVY_TIMEOUT_SECONDS = int(os.environ.get("API_HEAVY_TIMEOUT_SECONDS", "120"))

# Security settings
MIN_PASSPHRASE_LENGTH = int(os.environ.get("MIN_PASSPHRASE_LENGTH", "12"))
MIN_PASSPHRASE_ENTROPY = float(os.environ.get("MIN_PASSPHRASE_ENTROPY", "2.5"))

# API payload limits
MAX_UPLOAD_FILES_PER_BATCH = int(os.environ.get("MAX_UPLOAD_FILES_PER_BATCH", "20"))
MAX_CONSOLE_TEXT_CHARS = int(os.environ.get("MAX_CONSOLE_TEXT_CHARS", "200000"))
