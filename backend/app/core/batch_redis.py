"""
Layer Redis per la persistenza dei batch.

Gestisce la connessione Redis con fallback in-memory e tutte le operazioni
di lettura/scrittura/cancellazione dei dati di batch su Redis.

Questo modulo è interno al package core: usare batch_manager.py come API pubblica.
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional

from app.core.redis_utils import safe_redis_url
from app.models.schemas import Batch

logger = logging.getLogger(__name__)

# ─── Connessione Redis con retry interval ─────────────────────────────────────

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
    redis_url = safe_redis_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
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
    except Exception as e:
        logger.debug("Redis non disponibile (fallback in-memory attivo): %s", e)
        _redis_client_cached = None
        return None


# ─── Chiavi Redis ─────────────────────────────────────────────────────────────


def _redis_key(batch_id: str, suffix: str) -> str:
    return f"batch:{batch_id}:{suffix}"


def _redis_batch_ids_key() -> str:
    return "batch:ids"


# ─── Batch ────────────────────────────────────────────────────────────────────


def save_batch_to_redis(batch: Batch) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    payload = batch.model_dump_json() if hasattr(batch, "model_dump_json") else batch.json()
    redis_client.set(_redis_key(batch.batch_id, "meta"), payload)
    redis_client.sadd(_redis_batch_ids_key(), batch.batch_id)


def load_batch_from_redis(batch_id: str) -> Optional[Batch]:
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


# ─── Decisions ────────────────────────────────────────────────────────────────


def save_decisions_to_redis(batch_id: str, decisions: Dict[str, Any]) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    redis_client.set(_redis_key(batch_id, "decisions"), json.dumps(decisions, ensure_ascii=False))
    redis_client.sadd(_redis_batch_ids_key(), batch_id)


def load_decisions_from_redis(batch_id: str) -> Optional[Dict[str, Any]]:
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


# ─── Passphrase ───────────────────────────────────────────────────────────────


def save_passphrase_to_redis(batch_id: str, passphrase: str) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    redis_client.set(_redis_key(batch_id, "passphrase"), passphrase)
    redis_client.sadd(_redis_batch_ids_key(), batch_id)


def load_passphrase_from_redis(batch_id: str) -> Optional[str]:
    redis_client = _get_redis_client()
    if not redis_client:
        return None
    return redis_client.get(_redis_key(batch_id, "passphrase"))


# ─── Start time ───────────────────────────────────────────────────────────────


def save_start_time_to_redis(batch_id: str, started_at: str) -> None:
    redis_client = _get_redis_client()
    if not redis_client:
        return
    redis_client.set(_redis_key(batch_id, "started_at"), started_at)
    redis_client.sadd(_redis_batch_ids_key(), batch_id)


def load_start_time_from_redis(batch_id: str) -> Optional[str]:
    redis_client = _get_redis_client()
    if not redis_client:
        return None
    return redis_client.get(_redis_key(batch_id, "started_at"))


# ─── Delete ───────────────────────────────────────────────────────────────────


def delete_batch_from_redis(batch_id: str) -> None:
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


# ─── List all batch IDs from Redis ────────────────────────────────────────────


def list_batch_ids_from_redis() -> list:
    """Restituisce tutti i batch ID noti a Redis. Usato da list_batches()."""
    redis_client = _get_redis_client()
    if not redis_client:
        return []
    try:
        return list(redis_client.smembers(_redis_batch_ids_key()))
    except Exception as e:
        logger.warning("Errore durante list_batch_ids_from_redis: %s", e)
        return []
