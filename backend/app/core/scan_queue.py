"""
Coda asincrona per l'esecuzione delle scansioni batch.
Gestisce concorrenza limitata e deduplicazione dei job.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock

from app.core.batch_manager import get_batch, update_batch
from app.core.config import MAX_CONCURRENT_SCANS
from app.models.schemas import BatchStatus

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=max(1, MAX_CONCURRENT_SCANS), thread_name_prefix="scan-worker")
_queue_lock = Lock()
_inflight_batches: set[str] = set()


def enqueue_scan(batch_id: str, started_at: str | None = None) -> bool:
    """
    Inserisce un batch in coda per la scansione.
    Ritorna False se il batch è già in coda o in esecuzione.
    """
    with _queue_lock:
        if batch_id in _inflight_batches:
            return False
        _inflight_batches.add(batch_id)

    if not started_at:
        started_at = datetime.utcnow().isoformat()

    _executor.submit(_run_scan_job, batch_id, started_at)
    return True


def _run_scan_job(batch_id: str, started_at: str) -> None:
    try:
        batch = get_batch(batch_id)
        if not batch:
            logger.warning("Batch non trovato in scan queue: id=%s", batch_id)
            return

        batch.status = BatchStatus.SCANNING
        update_batch(batch)

        from app.core.pipeline import run_scan_pipeline

        run_scan_pipeline(batch_id)
        logger.info("Scan completata da worker per batch: id=%s", batch_id)

    except Exception as exc:
        logger.error("Errore worker scan per batch %s: %s", batch_id, exc)
        batch = get_batch(batch_id)
        if batch:
            batch.status = BatchStatus.ERROR
            batch.error_message = str(exc)
            update_batch(batch)
    finally:
        with _queue_lock:
            _inflight_batches.discard(batch_id)


def is_scan_inflight(batch_id: str) -> bool:
    with _queue_lock:
        return batch_id in _inflight_batches


def shutdown_scan_queue() -> None:
    _executor.shutdown(wait=False, cancel_futures=False)
