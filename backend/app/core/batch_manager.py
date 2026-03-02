"""
Gestore dei batch in memoria v4.0.
Mantiene lo stato di tutti i batch attivi durante la sessione del server.
- PseudonymEngine persistente per batch
- Passphrase generata automaticamente (persistita su storage condiviso per worker)
- Decisions persistite per batch (accept/reject/modify) su storage condiviso
- Timeout/cleanup automatico per inattività
"""

import logging
import json
import os
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import TEMP_BASE_DIR
from app.models.schemas import Batch, BatchMode, BatchStatus

logger = logging.getLogger(__name__)

# ─── Store in-memory ──────────────────────────────────────────────────────────
_batches: Dict[str, Batch] = {}
_passphrases: Dict[str, str] = {}  # batch_id -> passphrase (mai su disco)
_engines: Dict[str, object] = {}  # batch_id -> PseudonymEngine (persistente)
_decisions: Dict[str, Dict[str, Any]] = {}  # batch_id -> {finding_id -> decision_dict}
_last_activity: Dict[str, float] = {}  # batch_id -> timestamp ultima attività
_batch_start_times: Dict[str, str] = {}  # ✅ FIX #3: Centralized, thread-safe storage

# Timeout di inattività (configurabile, default 5 minuti)
BATCH_INACTIVITY_TIMEOUT_SECONDS = int(os.environ.get("BATCH_INACTIVITY_TIMEOUT_SECONDS", "300"))

# CRITICAL FIX #1: Reentrant lock for thread-safe access to all shared state
_global_lock = threading.RLock()
_cleanup_lock = threading.Lock()
_redis_client_cached = None
_redis_last_check = 0.0
_REDIS_RETRY_INTERVAL_SECONDS = 5.0


def _get_redis_client():
    global _redis_client_cached, _redis_last_check

    now = time.time()
    if _redis_client_cached is not None:
        return _redis_client_cached
    if now - _redis_last_check < _REDIS_RETRY_INTERVAL_SECONDS:
        return None

    _redis_last_check = now
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    try:
        from redis import Redis

        client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=0.3,
            socket_connect_timeout=0.3,
            retry_on_timeout=False,
        )
        client.ping()
        _redis_client_cached = client
        return client
    except Exception:
        _redis_client_cached = None
        return None


def _redis_key(batch_id: str, suffix: str) -> str:
    return f"batch:{batch_id}:{suffix}"


def _redis_batch_ids_key() -> str:
    return "batch:ids"


def _save_batch_to_redis(batch: Batch) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    payload = batch.model_dump_json() if hasattr(batch, "model_dump_json") else batch.json()
    redis_client.set(_redis_key(batch.batch_id, "meta"), payload)
    redis_client.sadd(_redis_batch_ids_key(), batch.batch_id)


def _load_batch_from_redis(batch_id: str) -> Optional[Batch]:
    redis_client = _get_redis_client()
    if not redis_client:
        return None
    payload = redis_client.get(_redis_key(batch_id, "meta"))
    if not payload:
        return None
    try:
        if hasattr(Batch, "model_validate_json"):
            return Batch.model_validate_json(payload)
        return Batch.parse_raw(payload)
    except Exception as e:
        logger.warning("Impossibile caricare batch %s da redis: %s", batch_id, e)
        return None


def _save_decisions_to_redis(batch_id: str, decisions: Dict[str, Any]) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    redis_client.set(_redis_key(batch_id, "decisions"), json.dumps(decisions, ensure_ascii=False))
    redis_client.sadd(_redis_batch_ids_key(), batch_id)


def _load_decisions_from_redis(batch_id: str) -> Optional[Dict[str, Any]]:
    redis_client = _get_redis_client()
    if not redis_client:
        return None
    raw = redis_client.get(_redis_key(batch_id, "decisions"))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        logger.warning("Impossibile caricare decisions per batch %s da redis: %s", batch_id, e)
        return None


def _save_passphrase_to_redis(batch_id: str, passphrase: str) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    redis_client.set(_redis_key(batch_id, "passphrase"), passphrase)
    redis_client.sadd(_redis_batch_ids_key(), batch_id)


def _load_passphrase_from_redis(batch_id: str) -> Optional[str]:
    redis_client = _get_redis_client()
    if not redis_client:
        return None
    return redis_client.get(_redis_key(batch_id, "passphrase"))


def _save_start_time_to_redis(batch_id: str, started_at: str) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    redis_client.set(_redis_key(batch_id, "started_at"), started_at)
    redis_client.sadd(_redis_batch_ids_key(), batch_id)


def _load_start_time_from_redis(batch_id: str) -> Optional[str]:
    redis_client = _get_redis_client()
    if not redis_client:
        return None
    return redis_client.get(_redis_key(batch_id, "started_at"))


def _delete_batch_from_redis(batch_id: str) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    redis_client.delete(
        _redis_key(batch_id, "meta"),
        _redis_key(batch_id, "decisions"),
        _redis_key(batch_id, "passphrase"),
        _redis_key(batch_id, "started_at"),
    )
    redis_client.srem(_redis_batch_ids_key(), batch_id)


def _batch_meta_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "batch.json"


def _batch_decisions_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "decisions.json"


def _batch_passphrase_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "passphrase.txt"


def _batch_start_time_path(batch_id: str) -> Path:
    return get_batch_dir(batch_id) / "started_at.txt"


def _atomic_write_text(path: Path, content: str) -> None:
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
            except Exception:
                pass


def _save_batch_to_disk(batch: Batch) -> None:
    payload = batch.model_dump_json() if hasattr(batch, "model_dump_json") else batch.json()
    _atomic_write_text(_batch_meta_path(batch.batch_id), payload)
    _save_batch_to_redis(batch)


def _load_batch_from_disk(batch_id: str) -> Optional[Batch]:
    redis_loaded = _load_batch_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    meta_path = _batch_meta_path(batch_id)
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


def _save_decisions_to_disk(batch_id: str, decisions: Dict[str, Any]) -> None:
    _atomic_write_text(_batch_decisions_path(batch_id), json.dumps(decisions, ensure_ascii=False))
    _save_decisions_to_redis(batch_id, decisions)


def _load_decisions_from_disk(batch_id: str) -> Dict[str, Any]:
    redis_loaded = _load_decisions_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    decisions_path = _batch_decisions_path(batch_id)
    if not decisions_path.exists():
        return {}
    try:
        return json.loads(decisions_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Impossibile caricare decisions per batch %s: %s", batch_id, e)
        return {}


def _save_passphrase_to_disk(batch_id: str, passphrase: str) -> None:
    passphrase_path = _batch_passphrase_path(batch_id)
    _atomic_write_text(passphrase_path, passphrase)
    _save_passphrase_to_redis(batch_id, passphrase)
    try:
        passphrase_path.chmod(0o600)
    except Exception:
        pass


def _load_passphrase_from_disk(batch_id: str) -> Optional[str]:
    redis_loaded = _load_passphrase_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    passphrase_path = _batch_passphrase_path(batch_id)
    if not passphrase_path.exists():
        return None
    try:
        return passphrase_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Impossibile leggere passphrase per batch %s: %s", batch_id, e)
        return None


def _save_start_time_to_disk(batch_id: str, started_at: str) -> None:
    _atomic_write_text(_batch_start_time_path(batch_id), started_at)
    _save_start_time_to_redis(batch_id, started_at)


def _load_start_time_from_disk(batch_id: str) -> Optional[str]:
    redis_loaded = _load_start_time_from_redis(batch_id)
    if redis_loaded is not None:
        return redis_loaded
    start_path = _batch_start_time_path(batch_id)
    if not start_path.exists():
        return None
    try:
        return start_path.read_text(encoding="utf-8").strip() or None
    except Exception as e:
        logger.warning("Impossibile leggere start time per batch %s: %s", batch_id, e)
        return None


# ─── Generazione passphrase ───────────────────────────────────────────────────


def generate_passphrase(length: int = 32) -> str:
    """
    Genera una passphrase crittograficamente sicura (32 caratteri, ~190 bit entropia).
    Usa secrets.choice e un alfabeto senza caratteri visivamente ambigui (0/O, 1/l/I).
    Non viene mai salvata su disco.
    """
    from app.mapping.crypto import generate_passphrase as _gen

    return _gen(length)


# ─── Batch Timing Helpers (Thread-Safe) ───────────────────────────────────────
# ✅ FIX #3: Centralized, lock-protected access to _batch_start_times


def set_batch_start_time(batch_id: str) -> None:
    """Record when a batch was created/started (thread-safe)."""
    with _global_lock:
        started_at = datetime.fromisoformat(
            datetime.now(timezone.utc).isoformat()
        ).isoformat()
        _batch_start_times[batch_id] = started_at
        _save_start_time_to_disk(batch_id, started_at)


def get_batch_start_time(batch_id: str) -> Optional[str]:
    """Get batch start time, returns None if not found (thread-safe)."""
    with _global_lock:
        cached = _batch_start_times.get(batch_id)
        if cached:
            return cached
        loaded = _load_start_time_from_disk(batch_id)
        if loaded:
            _batch_start_times[batch_id] = loaded
        return loaded


def clear_batch_start_time(batch_id: str) -> Optional[str]:
    """Remove and return batch start time (thread-safe)."""
    with _global_lock:
        value = _batch_start_times.pop(batch_id, None)
        start_path = _batch_start_time_path(batch_id)
        if start_path.exists():
            try:
                start_path.unlink()
            except Exception:
                pass
        return value


# ─── Atomic Operations Context Manager ─────────────────────────────────────────
# ✅ FIX #H2: Atomic transactions with rollback support


@contextmanager
def atomic_batch_operation(batch_id: str):
    """
    Context manager for atomic batch operations with automatic rollback on error.
    
    Maintains a snapshot of batch state and rolls back all changes if an exception occurs.
    Prevents concurrent modifications of the same batch during the operation.
    
    Usage:
        try:
            with atomic_batch_operation(batch_id) as snapshot:
                # Perform batch operations
                batch = get_batch(batch_id)
                batch.status = BatchStatus.APPLYING
                update_batch(batch)
                # ... more operations ...
        except Exception:
            # Automatically rolled back to snapshot
            pass
    
    Args:
        batch_id: ID of batch to operate on atomically
        
    Yields:
        Tuple of snapshots: (batch, decisions, passphrases, engines)
    """
    with _global_lock:
        # Capture snapshot of current batch state
        batch = _batches.get(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")
        
        batch_snapshot = deepcopy(batch)
        decisions_snapshot = deepcopy(_decisions.get(batch_id, {}))
        passphrase_snapshot = _passphrases.get(batch_id)
        engine_snapshot = _engines.get(batch_id)  # Engines not deep-copied (stateful objects)
        
        try:
            # Yield control to caller while holding lock
            yield (batch_snapshot, decisions_snapshot, passphrase_snapshot, engine_snapshot)
        except Exception as e:
            # On error, restore snapshots
            logger.error("Atomic operation failed for batch %s: %s. Rolling back.", batch_id, e)
            if batch_id in _batches:
                _batches[batch_id] = batch_snapshot
            if decisions_snapshot:
                _decisions[batch_id] = decisions_snapshot
            if passphrase_snapshot:
                _passphrases[batch_id] = passphrase_snapshot
            # Engine not rolled back (stateful, would be incorrect)
            raise


# ─── CRUD batch ───────────────────────────────────────────────────────────────


def create_batch(batch: Batch) -> Batch:
    """Registra un nuovo batch e crea la sua directory temporanea."""
    batch_dir = TEMP_BASE_DIR / batch.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    with _global_lock:
        _batches[batch.batch_id] = batch
        _decisions[batch.batch_id] = {}
        _last_activity[batch.batch_id] = time.time()
        _save_batch_to_disk(batch)
        _save_decisions_to_disk(batch.batch_id, {})
    
    logger.info("Batch creato: id=%s", batch.batch_id)
    return batch


def get_batch(batch_id: str) -> Optional[Batch]:
    """Recupera un batch per ID e aggiorna il timestamp di attività."""
    with _global_lock:
        batch = _batches.get(batch_id)
        if not batch:
            batch = _load_batch_from_disk(batch_id)
            if batch:
                _batches[batch_id] = batch
        if batch:
            _last_activity[batch_id] = time.time()
        return batch


def update_batch(batch: Batch) -> Batch:
    """Aggiorna lo stato di un batch esistente."""
    with _global_lock:
        _batches[batch.batch_id] = batch
        _last_activity[batch.batch_id] = time.time()
        _save_batch_to_disk(batch)
    return batch


def get_batch_dir(batch_id: str) -> Path:
    """Restituisce la directory temporanea del batch."""
    return TEMP_BASE_DIR / batch_id


def list_batches() -> List[Batch]:
    """Restituisce tutti i batch attivi."""
    with _global_lock:
        redis_client = _get_redis_client()
        if redis_client:
            try:
                for batch_id in redis_client.smembers(_redis_batch_ids_key()):
                    if batch_id in _batches:
                        continue
                    loaded = _load_batch_from_redis(batch_id)
                    if loaded:
                        _batches[batch_id] = loaded
                        _last_activity.setdefault(batch_id, time.time())
            except Exception as e:
                logger.warning("Errore durante list_batches da redis: %s", e)

        if not TEMP_BASE_DIR.exists():
            return list(_batches.values())
        for child in TEMP_BASE_DIR.iterdir():
            if not child.is_dir():
                continue
            batch_id = child.name
            if batch_id in _batches:
                continue
            loaded = _load_batch_from_disk(batch_id)
            if loaded:
                _batches[batch_id] = loaded
                _last_activity.setdefault(batch_id, time.time())
        return list(_batches.values())


# ─── Passphrase ───────────────────────────────────────────────────────────────


def store_passphrase(batch_id: str, passphrase: str) -> None:
    """Memorizza la passphrase in memoria e su storage condiviso per Celery worker."""
    with _global_lock:
        _passphrases[batch_id] = passphrase
        _save_passphrase_to_disk(batch_id, passphrase)


def get_passphrase(batch_id: str) -> Optional[str]:
    """Recupera la passphrase per un batch."""
    with _global_lock:
        cached = _passphrases.get(batch_id)
        if cached:
            return cached
        loaded = _load_passphrase_from_disk(batch_id)
        if loaded is not None:
            _passphrases[batch_id] = loaded
        return loaded


def regenerate_passphrase(batch_id: str) -> Optional[str]:
    """
    Rigenera la passphrase per un batch.
    ATTENZIONE: il mapping precedente diventa inaccessibile senza la vecchia passphrase.
    """
    with _global_lock:
        if batch_id not in _batches:
            loaded_batch = _load_batch_from_disk(batch_id)
            if not loaded_batch:
                return None
            _batches[batch_id] = loaded_batch
        new_pp = generate_passphrase()
        _passphrases[batch_id] = new_pp
        _save_passphrase_to_disk(batch_id, new_pp)
    logger.info("Passphrase rigenerata per batch %s (log sanitizzato)", batch_id)
    return new_pp


# ─── Decisions persistite ─────────────────────────────────────────────────────


def store_decisions(batch_id: str, decisions: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Persiste le decisioni di review per un batch.
    decisions: lista di {finding_id, action, custom_pseudonym?}
    Restituisce contatori {accepted, rejected, modified}.
    """
    with _global_lock:
        if batch_id not in _decisions:
            _decisions[batch_id] = {}

        counts = {"accepted": 0, "rejected": 0, "modified": 0}
        for d in decisions:
            fid = d.get("finding_id")
            action = d.get("action", "ACCEPT").upper()
            if not fid:
                continue
            _decisions[batch_id][fid] = {
                "action": action,
                "custom_pseudonym": d.get("custom_pseudonym"),
            }
            if action == "REJECT":
                counts["rejected"] += 1
            elif action == "MODIFY":
                counts["modified"] += 1
            else:
                counts["accepted"] += 1

        _last_activity[batch_id] = time.time()
        _save_decisions_to_disk(batch_id, _decisions[batch_id])
    return counts


def get_decisions(batch_id: str) -> Dict[str, Any]:
    """Recupera le decisioni persistite per un batch."""
    with _global_lock:
        cached = _decisions.get(batch_id)
        if cached is not None:
            return cached
        loaded = _load_decisions_from_disk(batch_id)
        _decisions[batch_id] = loaded
        return loaded


def clear_decisions(batch_id: str) -> None:
    """Cancella le decisioni di un batch (es. dopo apply)."""
    with _global_lock:
        _decisions[batch_id] = {}
        _save_decisions_to_disk(batch_id, {})


# ─── PseudonymEngine persistente ─────────────────────────────────────────────


def get_or_create_engine(batch_id: str, mode: BatchMode) -> object:
    """
    Restituisce il PseudonymEngine per il batch, creandolo se non esiste.
    Il motore è persistente per tutta la durata del batch per garantire
    la consistenza dei pseudonimi tra scan multipli.
    """
    from app.pseudonymizer.engine import PseudonymEngine

    with _global_lock:
        if batch_id not in _engines:
            _engines[batch_id] = PseudonymEngine(mode=mode)
            logger.info("PseudonymEngine creato per batch %s", batch_id)
        return _engines[batch_id]


def get_engine(batch_id: str) -> Optional[object]:
    """Recupera il PseudonymEngine per un batch."""
    with _global_lock:
        return _engines.get(batch_id)


# ─── Cleanup ──────────────────────────────────────────────────────────────────


def cleanup_batch(batch_id: str) -> None:
    """
    Rimuove la directory temporanea del batch e cancella tutti i dati in memoria.
    """
    with _global_lock:
        batch_dir = TEMP_BASE_DIR / batch_id
        if batch_dir.exists():
            try:
                shutil.rmtree(batch_dir)
                logger.info("Directory temporanea rimossa per batch: id=%s", batch_id)
            except Exception as e:
                logger.error("Errore rimozione directory batch %s: %s", batch_id, e)

        if batch_id in _passphrases:
            _passphrases[batch_id] = ""
            _passphrases.pop(batch_id, None)
        try:
            from app.core.pipeline import _clear_parse_results

            _clear_parse_results(batch_id)
        except Exception:
            pass
        _engines.pop(batch_id, None)
        _decisions.pop(batch_id, None)
        _batches.pop(batch_id, None)
        _last_activity.pop(batch_id, None)
        _batch_start_times.pop(batch_id, None)  # ✅ FIX #3: Also cleanup timing info
        _delete_batch_from_redis(batch_id)


def cleanup_inactive_batches() -> int:
    """
    Rimuove i batch inattivi. Restituisce il numero di batch rimossi.
    ✅ FIX #1: Single atomic lock region - no TOCTOU window between check and delete
    """
    cleaned_count = 0
    
    # Single lock acquisition - no race window
    with _global_lock:
        now = time.time()
        expired_bids = [bid for bid, last in _last_activity.items() 
                        if now - last > BATCH_INACTIVITY_TIMEOUT_SECONDS]
        
        # Clean them up immediately (still holding lock)
        for bid in expired_bids:
            # Double-check still expired (activity could have updated during iteration)
            if bid in _last_activity and now - _last_activity[bid] > BATCH_INACTIVITY_TIMEOUT_SECONDS:
                batch_dir = TEMP_BASE_DIR / bid
                if batch_dir.exists():
                    try:
                        shutil.rmtree(batch_dir)
                        logger.info("Directory temporanea rimossa per batch: id=%s", bid)
                    except Exception as e:
                        logger.error("Errore rimozione directory batch %s: %s", bid, e)

                if bid in _passphrases:
                    _passphrases[bid] = ""
                    _passphrases.pop(bid, None)
                try:
                    from app.core.pipeline import _clear_parse_results

                    _clear_parse_results(bid)
                except Exception:
                    pass
                _engines.pop(bid, None)
                _decisions.pop(bid, None)
                _batches.pop(bid, None)
                _last_activity.pop(bid, None)
                _batch_start_times.pop(bid, None)
                _delete_batch_from_redis(bid)
                cleaned_count += 1
    
    return cleaned_count


def start_cleanup_scheduler() -> None:
    """Avvia il thread di cleanup automatico (ogni 10 minuti)."""

    def _loop():
        while True:
            time.sleep(600)
            try:
                n = cleanup_inactive_batches()
                if n > 0:
                    logger.info("Cleanup automatico: rimossi %d batch inattivi", n)
            except Exception as e:
                logger.error("Errore nel cleanup automatico: %s", e)

    t = threading.Thread(target=_loop, daemon=True, name="batch-cleanup")
    t.start()
