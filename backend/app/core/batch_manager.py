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

# Timeout di inattività (configurabile)
BATCH_INACTIVITY_TIMEOUT_SECONDS = max(300, BATCH_INACTIVITY_TTL_HOURS * 3600)

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


# ─── CRUD batch ───────────────────────────────────────────────────────────────


def create_batch(batch: Batch) -> Batch:
    """Registra un nuovo batch e crea la sua directory temporanea."""
    batch_dir = TEMP_BASE_DIR / batch.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    _batches[batch.batch_id] = batch
    _decisions[batch.batch_id] = {}
    _last_activity[batch.batch_id] = time.time()
    logger.info("Batch creato: id=%s", batch.batch_id)
    return batch


def get_batch(batch_id: str) -> Optional[Batch]:
    """Recupera un batch per ID e aggiorna il timestamp di attività."""
    batch = _batches.get(batch_id)
    if batch:
        _last_activity[batch_id] = time.time()
    return batch


def update_batch(batch: Batch) -> Batch:
    """Aggiorna lo stato di un batch esistente."""
    _batches[batch.batch_id] = batch
    _last_activity[batch.batch_id] = time.time()
    return batch


def get_batch_dir(batch_id: str) -> Path:
    """Restituisce la directory temporanea del batch."""
    return TEMP_BASE_DIR / batch_id


def list_batches() -> List[Batch]:
    """Restituisce tutti i batch attivi."""
    return list(_batches.values())


# ─── Passphrase ───────────────────────────────────────────────────────────────


def store_passphrase(batch_id: str, passphrase: str) -> None:
    """Memorizza la passphrase in memoria (mai su disco)."""
    _passphrases[batch_id] = passphrase


def get_passphrase(batch_id: str) -> Optional[str]:
    """Recupera la passphrase per un batch."""
    return _passphrases.get(batch_id)


def regenerate_passphrase(batch_id: str) -> Optional[str]:
    """
    Rigenera la passphrase per un batch.
    ATTENZIONE: il mapping precedente diventa inaccessibile senza la vecchia passphrase.
    """
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
    return _decisions.get(batch_id, {})


def clear_decisions(batch_id: str) -> None:
    """Cancella le decisioni di un batch (es. dopo apply)."""
    _decisions[batch_id] = {}


# ─── PseudonymEngine persistente ─────────────────────────────────────────────


def get_or_create_engine(batch_id: str, mode: BatchMode) -> object:
    """
    Restituisce il PseudonymEngine per il batch, creandolo se non esiste.
    Il motore è persistente per tutta la durata del batch per garantire
    la consistenza dei pseudonimi tra scan multipli.
    """
    from app.pseudonymizer.engine import PseudonymEngine

    if batch_id not in _engines:
        _engines[batch_id] = PseudonymEngine(mode=mode)
        logger.info("PseudonymEngine creato per batch %s", batch_id)
    return _engines[batch_id]


def get_engine(batch_id: str) -> Optional[object]:
    """Recupera il PseudonymEngine per un batch."""
    return _engines.get(batch_id)


# ─── Cleanup ──────────────────────────────────────────────────────────────────


def cleanup_batch(batch_id: str) -> None:
    """
    Rimuove la directory temporanea del batch e cancella tutti i dati in memoria.
    """
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


def cleanup_inactive_batches() -> int:
    """Rimuove i batch inattivi. Restituisce il numero di batch rimossi."""
    with _cleanup_lock:
        now = time.time()
        expired = [bid for bid, last in _last_activity.items() if now - last > BATCH_INACTIVITY_TIMEOUT_SECONDS]
        for bid in expired:
            logger.info("Cleanup batch inattivo: %s", bid)
            cleanup_batch(bid)
        return len(expired)


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
