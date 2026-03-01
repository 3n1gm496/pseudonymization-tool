"""
Gestore dei batch in memoria v4.0.
Mantiene lo stato di tutti i batch attivi durante la sessione del server.
- PseudonymEngine persistente per batch
- Passphrase generata automaticamente (mai su disco)
- Decisions persistite per batch (accept/reject/modify)
- Timeout/cleanup automatico per inattività
"""

import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import BATCH_INACTIVITY_TTL_HOURS, TEMP_BASE_DIR
from app.models.schemas import Batch, BatchMode, BatchStatus

logger = logging.getLogger(__name__)

# ─── Store in-memory ──────────────────────────────────────────────────────────
_batches: Dict[str, Batch] = {}
_passphrases: Dict[str, str] = {}  # batch_id -> passphrase (mai su disco)
_engines: Dict[str, object] = {}  # batch_id -> PseudonymEngine (persistente)
_decisions: Dict[str, Dict[str, Any]] = {}  # batch_id -> {finding_id -> decision_dict}
_last_activity: Dict[str, float] = {}  # batch_id -> timestamp ultima attività
_batch_start_times: Dict[str, str] = {}  # ✅ FIX #3: Centralized, thread-safe storage

# Timeout di inattività (configurabile)
BATCH_INACTIVITY_TIMEOUT_SECONDS = max(300, BATCH_INACTIVITY_TTL_HOURS * 3600)

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
# ✅ FIX #3: Centralized, lock-protected access to _batch_start_times


def set_batch_start_time(batch_id: str) -> None:
    """Record when a batch was created/started (thread-safe)."""
    with _global_lock:
        _batch_start_times[batch_id] = datetime.fromisoformat(
            datetime.now(timezone.utc).isoformat()
        ).isoformat()


def get_batch_start_time(batch_id: str) -> Optional[str]:
    """Get batch start time, returns None if not found (thread-safe)."""
    with _global_lock:
        return _batch_start_times.get(batch_id)


def clear_batch_start_time(batch_id: str) -> Optional[str]:
    """Remove and return batch start time (thread-safe)."""
    with _global_lock:
        return _batch_start_times.pop(batch_id, None)


# ─── CRUD batch ───────────────────────────────────────────────────────────────


def create_batch(batch: Batch) -> Batch:
    """Registra un nuovo batch e crea la sua directory temporanea."""
    batch_dir = TEMP_BASE_DIR / batch.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    with _global_lock:
        _batches[batch.batch_id] = batch
        _decisions[batch.batch_id] = {}
        _last_activity[batch.batch_id] = time.time()
    
    logger.info("Batch creato: id=%s", batch.batch_id)
    return batch


def get_batch(batch_id: str) -> Optional[Batch]:
    """Recupera un batch per ID e aggiorna il timestamp di attività."""
    with _global_lock:
        batch = _batches.get(batch_id)
        if batch:
            _last_activity[batch_id] = time.time()
        return batch


def update_batch(batch: Batch) -> Batch:
    """Aggiorna lo stato di un batch esistente."""
    with _global_lock:
        _batches[batch.batch_id] = batch
        _last_activity[batch.batch_id] = time.time()
    return batch


def get_batch_dir(batch_id: str) -> Path:
    """Restituisce la directory temporanea del batch."""
    return TEMP_BASE_DIR / batch_id


def list_batches() -> List[Batch]:
    """Restituisce tutti i batch attivi."""
    with _global_lock:
        return list(_batches.values())


# ─── Passphrase ───────────────────────────────────────────────────────────────


def store_passphrase(batch_id: str, passphrase: str) -> None:
    """Memorizza la passphrase in memoria (mai su disco)."""
    with _global_lock:
        _passphrases[batch_id] = passphrase


def get_passphrase(batch_id: str) -> Optional[str]:
    """Recupera la passphrase per un batch."""
    with _global_lock:
        return _passphrases.get(batch_id)


def regenerate_passphrase(batch_id: str) -> Optional[str]:
    """
    Rigenera la passphrase per un batch.
    ATTENZIONE: il mapping precedente diventa inaccessibile senza la vecchia passphrase.
    """
    with _global_lock:
        if batch_id not in _batches:
            return None
        new_pp = generate_passphrase()
        _passphrases[batch_id] = new_pp
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
    return counts


def get_decisions(batch_id: str) -> Dict[str, Any]:
    """Recupera le decisioni persistite per un batch."""
    with _global_lock:
        return _decisions.get(batch_id, {})


def clear_decisions(batch_id: str) -> None:
    """Cancella le decisioni di un batch (es. dopo apply)."""
    with _global_lock:
        _decisions[batch_id] = {}


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


def cleanup_inactive_batches() -> int:
    """
    Rimuove i batch inattivi. Restituisce il numero di batch rimossi.
    ✅ FIX: Check expiration INSIDE _global_lock to prevent TOCTOU race condition
    """
    expired_bids = []
    
    # Step 1: Identify expired batches (under main lock to prevent TOCTOU)
    with _global_lock:
        now = time.time()
        expired_bids = [bid for bid, last in _last_activity.items() 
                        if now - last > BATCH_INACTIVITY_TIMEOUT_SECONDS]
    
    # Step 2: Clean them up (still under same lock context)
    if expired_bids:
        with _global_lock:
            # Double-check expiration is still valid (re-check under lock)
            now = time.time()
            for bid in expired_bids:
                if bid in _last_activity and now - _last_activity[bid] > BATCH_INACTIVITY_TIMEOUT_SECONDS:
                    # Only cleanup if still expired
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
    
    return len(expired_bids)


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
