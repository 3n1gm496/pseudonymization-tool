"""
Gestore dei batch in memoria.
Mantiene lo stato di tutti i batch attivi durante la sessione del server.
"""
import shutil
import logging
from typing import Dict, Optional
from pathlib import Path

from app.models.schemas import Batch, BatchStatus
from app.core.config import TEMP_BASE_DIR

logger = logging.getLogger(__name__)

# Store in-memory dei batch attivi
_batches: Dict[str, Batch] = {}
# Store delle passphrase in memoria (mai su disco)
_passphrases: Dict[str, str] = {}


def create_batch(batch: Batch) -> Batch:
    """Registra un nuovo batch e crea la sua directory temporanea."""
    batch_dir = TEMP_BASE_DIR / batch.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    _batches[batch.batch_id] = batch
    logger.info("Batch creato: id=%s", batch.batch_id)
    return batch


def get_batch(batch_id: str) -> Optional[Batch]:
    """Recupera un batch per ID."""
    return _batches.get(batch_id)


def update_batch(batch: Batch) -> Batch:
    """Aggiorna lo stato di un batch esistente."""
    _batches[batch.batch_id] = batch
    return batch


def store_passphrase(batch_id: str, passphrase: str) -> None:
    """Memorizza la passphrase in memoria (mai su disco)."""
    _passphrases[batch_id] = passphrase


def get_passphrase(batch_id: str) -> Optional[str]:
    """Recupera la passphrase per un batch."""
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
    _passphrases.pop(batch_id, None)

    # Rimuovi il batch dallo store
    _batches.pop(batch_id, None)
