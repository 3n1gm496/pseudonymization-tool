"""
Gestore dei batch in memoria.
Mantiene lo stato di tutti i batch attivi durante la sessione del server.
"""
import shutil
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
from pathlib import Path
from threading import RLock

from app.models.schemas import Batch
from app.core.config import TEMP_BASE_DIR, BATCH_INACTIVITY_TTL_HOURS

logger = logging.getLogger(__name__)

# Store in-memory dei batch attivi
_batches: Dict[str, Batch] = {}
# Store delle passphrase in memoria (mai su disco)
_passphrases: Dict[str, str] = {}
_store_lock = RLock()


def create_batch(batch: Batch) -> Batch:
    """Registra un nuovo batch e crea la sua directory temporanea."""
    batch_dir = TEMP_BASE_DIR / batch.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    with _store_lock:
        _batches[batch.batch_id] = batch
    logger.info("Batch creato: id=%s", batch.batch_id)
    return batch


def get_batch(batch_id: str) -> Optional[Batch]:
    """Recupera un batch per ID."""
    with _store_lock:
        return _batches.get(batch_id)


def update_batch(batch: Batch) -> Batch:
    """Aggiorna lo stato di un batch esistente e aggiorna last_activity_at."""
    batch.last_activity_at = datetime.now(timezone.utc).isoformat()
    with _store_lock:
        _batches[batch.batch_id] = batch
    return batch


def store_passphrase(batch_id: str, passphrase: str) -> None:
    """Memorizza la passphrase in memoria (mai su disco)."""
    with _store_lock:
        _passphrases[batch_id] = passphrase


def get_passphrase(batch_id: str) -> Optional[str]:
    """Recupera la passphrase per un batch."""
    with _store_lock:
        return _passphrases.get(batch_id)


def get_batch_dir(batch_id: str) -> Path:
    """Restituisce la directory temporanea del batch."""
    return TEMP_BASE_DIR / batch_id


def cleanup_batch(batch_id: str) -> None:
    """
    Rimuove la directory temporanea del batch e cancella la passphrase dalla memoria.
    Questa funzione viene chiamata dopo il download degli artefatti o in caso di errore.
    """
    batch_dir = TEMP_BASE_DIR / batch_id
    if batch_dir.exists():
        try:
            shutil.rmtree(batch_dir)
            logger.info("Directory temporanea rimossa per batch: id=%s", batch_id)
        except Exception as e:
            logger.error("Errore nella rimozione della directory del batch %s: %s", batch_id, e)

    # Rimuovi la passphrase dalla memoria
    with _store_lock:
        _passphrases.pop(batch_id, None)

    # Rimuovi il batch dallo store
    with _store_lock:
        _batches.pop(batch_id, None)


def get_inactive_batch_ids() -> List[str]:
    """
    Restituisce gli ID dei batch inattivi oltre il TTL configurato.
    Un batch è considerato inattivo se last_activity_at è più vecchio di BATCH_INACTIVITY_TTL_HOURS.
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=BATCH_INACTIVITY_TTL_HOURS)
    inactive_ids = []
    
    with _store_lock:
        for batch_id, batch in _batches.items():
            try:
                last_activity = datetime.fromisoformat(batch.last_activity_at.replace('Z', '+00:00'))
                if last_activity < cutoff_time:
                    inactive_ids.append(batch_id)
            except Exception as e:
                logger.warning(f"Errore parsing last_activity_at per batch {batch_id}: {e}")
    
    return inactive_ids


def cleanup_inactive_batches() -> int:
    """
    Esegue il garbage collection dei batch inattivi.
    Restituisce il numero di batch puliti.
    """
    inactive_ids = get_inactive_batch_ids()
    
    if not inactive_ids:
        return 0
    
    logger.info(f"Garbage collection: trovati {len(inactive_ids)} batch inattivi da rimuovere")
    
    for batch_id in inactive_ids:
        try:
            cleanup_batch(batch_id)
            logger.info(f"Batch inattivo rimosso: {batch_id}")
        except Exception as e:
            logger.error(f"Errore durante cleanup batch {batch_id}: {e}")
    
    return len(inactive_ids)


def get_all_batch_ids() -> List[str]:
    """Restituisce tutti gli ID dei batch attivi."""
    with _store_lock:
        return list(_batches.keys())
