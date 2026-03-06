"""
Gestore dei batch in memoria v5.1.0.

Mantiene lo stato di tutti i batch attivi durante la sessione del server.
- PseudonymEngine persistente per batch
- Passphrase generata automaticamente (persistita su storage condiviso per worker)
- Decisions persistite per batch (accept/reject/modify) su storage condiviso
- Timeout/cleanup automatico per inattività

Architettura interna (refactoring v5.1.0):
  batch_redis.py       — layer Redis (connessione, CRUD su Redis)
  batch_persistence.py — layer filesystem (scrittura atomica, cifratura passphrase)
  batch_manager.py     — logica di business (CRUD batch, cleanup, scheduler)
"""

import logging
import os
import shutil
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.batch_persistence import (  # noqa: F401
    _UUID_RE,
    batch_start_time_path,
    get_batch_dir,
    load_batch_from_disk,
    load_decisions_from_disk,
    load_passphrase_from_disk,
    load_start_time_from_disk,
    save_batch_to_disk,
    save_decisions_to_disk,
    save_passphrase_to_disk,
    save_start_time_to_disk,
)
from app.core.batch_redis import delete_batch_from_redis, list_batch_ids_from_redis, load_batch_from_redis
from app.core.config import TEMP_BASE_DIR
from app.models.schemas import Batch, BatchMode, BatchStatus

logger = logging.getLogger(__name__)

# ─── Store in-memory ──────────────────────────────────────────────────────────
_batches: Dict[str, Batch] = {}
_passphrases: Dict[str, str] = {}  # batch_id -> passphrase (in memoria e Redis; su disco cifrata con AUTH_SECRET)
_engines: Dict[str, object] = {}  # batch_id -> PseudonymEngine (persistente)
_decisions: Dict[str, Dict[str, Any]] = {}  # batch_id -> {finding_id -> decision_dict}
_last_activity: Dict[str, float] = {}  # batch_id -> timestamp ultima attività
_batch_start_times: Dict[str, str] = {}  # Centralized, thread-safe storage

# Timeout di inattività (configurabile, default 5 minuti)
BATCH_INACTIVITY_TIMEOUT_SECONDS = int(os.environ.get("BATCH_INACTIVITY_TIMEOUT_SECONDS", "300"))

# CRITICAL FIX #1: Reentrant lock for thread-safe access to all shared state
_global_lock = threading.RLock()
_cleanup_lock = threading.Lock()


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
# Centralized, lock-protected access to _batch_start_times


def set_batch_start_time(batch_id: str) -> None:
    """Record when a batch was created/started (thread-safe)."""
    with _global_lock:
        started_at = datetime.fromisoformat(datetime.now(timezone.utc).isoformat()).isoformat()
        _batch_start_times[batch_id] = started_at
        save_start_time_to_disk(batch_id, started_at)


def get_batch_start_time(batch_id: str) -> Optional[str]:
    """Get batch start time, returns None if not found (thread-safe)."""
    with _global_lock:
        cached = _batch_start_times.get(batch_id)
        if cached:
            return cached
        loaded = load_start_time_from_disk(batch_id)
        if loaded:
            _batch_start_times[batch_id] = loaded
        return loaded


def clear_batch_start_time(batch_id: str) -> Optional[str]:
    """Remove and return batch start time (thread-safe)."""
    with _global_lock:
        value = _batch_start_times.pop(batch_id, None)
        start_path = batch_start_time_path(batch_id)
        if start_path.exists():
            try:
                start_path.unlink()
            except Exception as e:
                logger.warning("Impossibile rimuovere il file start_time %s: %s", start_path, e)
        return value


# ─── Atomic Operations Context Manager ─────────────────────────────────────────
# Atomic transactions with rollback support


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
        save_batch_to_disk(batch)
        save_decisions_to_disk(batch.batch_id, {})

    logger.info("Batch creato: id=%s", batch.batch_id)
    return batch


# Stati transitori in cui il batch può essere aggiornato da un processo esterno
# (Celery worker). In questi stati la cache in-memory non è affidabile e
# occorre rileggere sempre da Redis/disco per ottenere lo stato aggiornato.
_TRANSIENT_STATUSES = frozenset(
    {
        BatchStatus.PENDING,
        BatchStatus.SCANNING,
        BatchStatus.APPLYING,
    }
)


def get_batch(batch_id: str) -> Optional[Batch]:
    """Recupera un batch per ID e aggiorna il timestamp di attività.

    Per i batch in stato transitorio (pending/scanning/applying) rilegge sempre
    da Redis/disco, perché il Celery worker (processo separato) potrebbe aver
    aggiornato lo stato senza che la cache in-memory del processo FastAPI ne
    sia a conoscenza.
    """
    with _global_lock:
        cached = _batches.get(batch_id)
        if cached and cached.status not in _TRANSIENT_STATUSES:
            # Stato stabile: la cache è affidabile
            _last_activity[batch_id] = time.time()
            return cached
        # Stato transitorio o batch non in cache: rileggi da Redis/disco
        batch = load_batch_from_disk(batch_id)
        if batch:
            _batches[batch_id] = batch
            _last_activity[batch_id] = time.time()
        elif cached:
            # Fallback alla cache se il disco non risponde
            _last_activity[batch_id] = time.time()
            return cached
        return batch


def update_batch(batch: Batch) -> Batch:
    """Aggiorna lo stato di un batch esistente."""
    with _global_lock:
        _batches[batch.batch_id] = batch
        _last_activity[batch.batch_id] = time.time()
        save_batch_to_disk(batch)
    return batch


def list_batches() -> List[Batch]:
    """Restituisce tutti i batch attivi."""
    with _global_lock:
        for batch_id in list_batch_ids_from_redis():
            if batch_id in _batches:
                continue
            loaded = load_batch_from_redis(batch_id)
            if loaded:
                _batches[batch_id] = loaded
                _last_activity.setdefault(batch_id, time.time())

        if not TEMP_BASE_DIR.exists():
            return list(_batches.values())
        for child in TEMP_BASE_DIR.iterdir():
            if not child.is_dir():
                continue
            batch_id = child.name
            if not _UUID_RE.match(batch_id):
                continue
            if batch_id in _batches:
                continue
            loaded = load_batch_from_disk(batch_id)
            if loaded:
                _batches[batch_id] = loaded
                _last_activity.setdefault(batch_id, time.time())
        return list(_batches.values())


# ─── Passphrase ───────────────────────────────────────────────────────────────


def store_passphrase(batch_id: str, passphrase: str) -> None:
    """Memorizza la passphrase in memoria e su storage condiviso per Celery worker."""
    with _global_lock:
        _passphrases[batch_id] = passphrase
        save_passphrase_to_disk(batch_id, passphrase)


def get_passphrase(batch_id: str) -> Optional[str]:
    """Recupera la passphrase per un batch."""
    with _global_lock:
        cached = _passphrases.get(batch_id)
        if cached:
            return cached
        loaded = load_passphrase_from_disk(batch_id)
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
            loaded_batch = load_batch_from_disk(batch_id)
            if not loaded_batch:
                return None
            _batches[batch_id] = loaded_batch
        new_pp = generate_passphrase()
        _passphrases[batch_id] = new_pp
        save_passphrase_to_disk(batch_id, new_pp)
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
        save_decisions_to_disk(batch_id, _decisions[batch_id])
    return counts


def get_decisions(batch_id: str) -> Dict[str, Any]:
    """Recupera le decisioni persistite per un batch."""
    with _global_lock:
        cached = _decisions.get(batch_id)
        if cached is not None:
            return cached
        loaded = load_decisions_from_disk(batch_id)
        _decisions[batch_id] = loaded
        return loaded


def clear_decisions(batch_id: str) -> None:
    """Cancella le decisioni di un batch (es. dopo apply)."""
    with _global_lock:
        _decisions[batch_id] = {}
        save_decisions_to_disk(batch_id, {})


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

        _passphrases.pop(batch_id, None)
        try:
            from app.core.pipeline import _clear_parse_results

            _clear_parse_results(batch_id)
        except Exception as e:
            logger.warning(
                "Cleanup parziale: impossibile rimuovere i risultati di parsing per batch %s: %s",
                batch_id,
                e,
            )
        _engines.pop(batch_id, None)
        _decisions.pop(batch_id, None)
        _batches.pop(batch_id, None)
        _last_activity.pop(batch_id, None)
        _batch_start_times.pop(batch_id, None)  # Also cleanup timing info
        delete_batch_from_redis(batch_id)


def cleanup_inactive_batches() -> int:
    """
    Rimuove i batch inattivi. Restituisce il numero di batch rimossi.
    Single atomic lock region - no TOCTOU window between check and delete
    """
    cleaned_count = 0

    # Single lock acquisition - no race window
    with _global_lock:
        now = time.time()
        expired_bids = [bid for bid, last in _last_activity.items() if now - last > BATCH_INACTIVITY_TIMEOUT_SECONDS]

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

                _passphrases.pop(bid, None)
                try:
                    from app.core.pipeline import _clear_parse_results

                    _clear_parse_results(bid)
                except Exception as e:
                    logger.warning(
                        "Cleanup timeout: impossibile rimuovere i risultati di parsing per batch %s: %s",
                        bid,
                        e,
                    )
                _engines.pop(bid, None)
                _decisions.pop(bid, None)
                _batches.pop(bid, None)
                _last_activity.pop(bid, None)
                _batch_start_times.pop(bid, None)
                delete_batch_from_redis(bid)
                cleaned_count += 1

    return cleaned_count


# Event per il graceful shutdown del cleanup scheduler
_cleanup_stop_event = threading.Event()


def start_cleanup_scheduler() -> None:
    """Avvia il thread di cleanup automatico (ogni 10 minuti)."""
    _cleanup_stop_event.clear()

    def _loop():
        # Usa wait(timeout) invece di sleep: si sveglia immediatamente su stop_event.set()
        while not _cleanup_stop_event.wait(timeout=600):
            try:
                n = cleanup_inactive_batches()
                if n > 0:
                    logger.info("Cleanup automatico: rimossi %d batch inattivi", n)
            except Exception as e:
                logger.error("Errore nel cleanup automatico: %s", e)
        logger.info("Cleanup scheduler terminato (graceful shutdown).")

    t = threading.Thread(target=_loop, daemon=True, name="batch-cleanup")
    t.start()


def stop_cleanup_scheduler() -> None:
    """Ferma il thread di cleanup automatico in modo pulito (graceful shutdown).

    Segnala al thread di terminare senza attendere il prossimo ciclo di 10 minuti.
    Il thread termina entro pochi millisecondi dopo la chiamata.
    """
    _cleanup_stop_event.set()
