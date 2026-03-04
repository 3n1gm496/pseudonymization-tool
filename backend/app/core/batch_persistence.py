"""
Layer di persistenza su filesystem per i batch.

Gestisce la scrittura/lettura atomica su disco di tutti i dati di batch:
metadati, decisions, passphrase cifrate e start time.

La passphrase viene cifrata con AES-256-GCM usando AUTH_SECRET come chiave,
in modo che il file su disco sia inutilizzabile senza il segreto del server.

Questo modulo è interno al package core: usare batch_manager.py come API pubblica.
"""

import json
import logging
import os
import re as _re
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.batch_redis import (
    load_batch_from_redis,
    load_decisions_from_redis,
    load_passphrase_from_redis,
    load_start_time_from_redis,
    save_batch_to_redis,
    save_decisions_to_redis,
    save_passphrase_to_redis,
    save_start_time_to_redis,
)
from app.core.config import TEMP_BASE_DIR
from app.models.schemas import Batch

logger = logging.getLogger(__name__)


# ─── Path helpers ─────────────────────────────────────────────────────────────


def batch_meta_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "batch.json"


def batch_decisions_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "decisions.json"


def batch_passphrase_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "passphrase.txt"


def batch_start_time_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "started_at.txt"


_UUID_RE = _re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    _re.IGNORECASE,
)


def get_batch_dir(batch_id: str) -> Path:
    """Restituisce la directory temporanea del batch."""
    if not _UUID_RE.match(batch_id):
        raise ValueError(f"Invalid batch_id format: {batch_id!r}")
    return TEMP_BASE_DIR / batch_id


# ─── Scrittura atomica ────────────────────────────────────────────────────────


def atomic_write_text(path: Path, content: str) -> None:
    """
    Scrive `content` in `path` in modo atomico usando rename.
    Garantisce che il file non sia mai in uno stato parzialmente scritto.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_path = Path(handle.name)
        tmp_path.replace(path)
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception as e:
                logger.warning("Impossibile rimuovere il file temporaneo %s: %s", tmp_path, e)


# ─── Cifratura passphrase ─────────────────────────────────────────────────────


def encrypt_passphrase_for_disk(passphrase: str) -> str:
    """
    Cifra la passphrase con AES-256-GCM usando l'AUTH_SECRET come chiave.
    La passphrase su disco è inutilizzabile senza l'AUTH_SECRET del server.
    Restituisce una stringa base64url-safe.
    """
    import base64
    import hashlib

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    auth_secret = os.environ.get("AUTH_SECRET", "")
    if not auth_secret:
        raise ValueError("AUTH_SECRET non configurato: impossibile cifrare la passphrase per il disco")
    key = hashlib.sha256(auth_secret.encode("utf-8")).digest()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, passphrase.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_passphrase_from_disk(encrypted: str) -> Optional[str]:
    """
    Decifra la passphrase letta dal disco.
    Restituisce None se AUTH_SECRET non è configurato o la decifratura fallisce.
    """
    import base64
    import hashlib

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    auth_secret = os.environ.get("AUTH_SECRET", "")
    if not auth_secret:
        logger.warning("AUTH_SECRET non configurato: impossibile decifrare la passphrase dal disco")
        return None
    try:
        raw = base64.urlsafe_b64decode(encrypted.encode("ascii"))
        key = hashlib.sha256(auth_secret.encode("utf-8")).digest()
        nonce, ciphertext = raw[:12], raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as e:
        logger.warning("Impossibile decifrare passphrase dal disco: %s", e)
        return None


# ─── Batch ────────────────────────────────────────────────────────────────────


def save_batch_to_disk(batch: Batch) -> None:
    payload = batch.model_dump_json() if hasattr(batch, "model_dump_json") else batch.json()
    atomic_write_text(batch_meta_path(batch.batch_id), payload)
    save_batch_to_redis(batch)


def load_batch_from_disk(batch_id: str) -> Optional[Batch]:
    redis_loaded = load_batch_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    try:
        meta_path = batch_meta_path(batch_id)
    except ValueError:
        return None
    if not meta_path.exists():
        return None
    try:
        payload = meta_path.read_text(encoding="utf-8")
        if hasattr(Batch, "model_validate_json"):
            return Batch.model_validate_json(payload)
        return Batch.parse_raw(payload)
    except Exception as e:
        logger.warning("Impossibile caricare batch %s da disco: %s", batch_id, e)
        return None


# ─── Decisions ────────────────────────────────────────────────────────────────


def save_decisions_to_disk(batch_id: str, decisions: Dict[str, Any]) -> None:
    atomic_write_text(batch_decisions_path(batch_id), json.dumps(decisions, ensure_ascii=False))
    save_decisions_to_redis(batch_id, decisions)


def load_decisions_from_disk(batch_id: str) -> Dict[str, Any]:
    redis_loaded = load_decisions_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    try:
        decisions_path = batch_decisions_path(batch_id)
    except ValueError:
        return {}
    if not decisions_path.exists():
        return {}
    try:
        return json.loads(decisions_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Impossibile caricare decisions per batch %s: %s", batch_id, e)
        return {}


# ─── Passphrase ───────────────────────────────────────────────────────────────


def save_passphrase_to_disk(batch_id: str, passphrase: str) -> None:
    save_passphrase_to_redis(batch_id, passphrase)
    try:
        encrypted = encrypt_passphrase_for_disk(passphrase)
    except ValueError as e:
        logger.warning("Passphrase non salvata su disco per batch %s: %s", batch_id, e)
        return
    passphrase_path = batch_passphrase_path(batch_id)
    atomic_write_text(passphrase_path, encrypted)
    try:
        passphrase_path.chmod(0o600)
    except Exception as e:
        logger.warning("Impossibile impostare permessi 0o600 su %s: %s", passphrase_path, e)


def load_passphrase_from_disk(batch_id: str) -> Optional[str]:
    redis_loaded = load_passphrase_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    try:
        passphrase_path = batch_passphrase_path(batch_id)
    except ValueError:
        return None
    if not passphrase_path.exists():
        return None
    try:
        encrypted = passphrase_path.read_text(encoding="utf-8").strip()
        return decrypt_passphrase_from_disk(encrypted)
    except Exception as e:
        logger.warning("Impossibile leggere passphrase per batch %s: %s", batch_id, e)
        return None


# ─── Start time ───────────────────────────────────────────────────────────────


def save_start_time_to_disk(batch_id: str, started_at: str) -> None:
    atomic_write_text(batch_start_time_path(batch_id), started_at)
    save_start_time_to_redis(batch_id, started_at)


def load_start_time_from_disk(batch_id: str) -> Optional[str]:
    redis_loaded = load_start_time_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    try:
        start_path = batch_start_time_path(batch_id)
    except ValueError:
        return None
    if not start_path.exists():
        return None
    try:
        return start_path.read_text(encoding="utf-8").strip() or None
    except Exception as e:
        logger.warning("Impossibile leggere start time per batch %s: %s", batch_id, e)
        return None
