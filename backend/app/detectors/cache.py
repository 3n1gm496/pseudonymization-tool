"""
Cache per i risultati dei detector con TTL e LRU eviction.
"""

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import DETECTOR_CACHE_ENABLED, DETECTOR_CACHE_MAX_SIZE, DETECTOR_CACHE_TTL_SECONDS
from app.detectors.base import RawFinding

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Entry del cache con TTL."""

    findings: List[RawFinding]
    timestamp: float
    hits: int = 0


class DetectorCache:
    """
    Cache LRU con TTL per i risultati dei detector.
    Thread-safe per accessi multipli concorrenti.
    """

    def __init__(self, max_size: int = DETECTOR_CACHE_MAX_SIZE, ttl_seconds: int = DETECTOR_CACHE_TTL_SECONDS):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._enabled = DETECTOR_CACHE_ENABLED
        self._hits = 0
        self._misses = 0

    def _compute_key(self, text: str, chunk_id: str) -> str:
        """Genera una chiave hash per il testo del chunk."""
        combined = f"{chunk_id}:{text}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Verifica se l'entry è scaduta."""
        return (time.time() - entry.timestamp) > self.ttl_seconds

    def get(self, text: str, chunk_id: str) -> Optional[List[RawFinding]]:
        """
        Recupera i risultati dal cache.
        Ritorna None se non trovato o scaduto.
        """
        if not self._enabled:
            return None

        key = self._compute_key(text, chunk_id)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        if self._is_expired(entry):
            # Entry scaduta, rimuovila
            del self._cache[key]
            self._misses += 1
            return None

        # Cache hit - muovi in fondo (LRU)
        self._cache.move_to_end(key)
        entry.hits += 1
        self._hits += 1

        logger.debug("Cache hit per chunk %s (hits: %d)", chunk_id, entry.hits)
        return entry.findings

    def put(self, text: str, chunk_id: str, findings: List[RawFinding]) -> None:
        """Salva i risultati nel cache."""
        if not self._enabled:
            return

        key = self._compute_key(text, chunk_id)

        # Se cache pieno, rimuovi l'elemento più vecchio (LRU)
        if len(self._cache) >= self.max_size and key not in self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug("Cache eviction: rimosso %s (size: %d)", oldest_key[:8], len(self._cache))

        # Aggiungi o aggiorna entry
        entry = CacheEntry(findings=findings, timestamp=time.time(), hits=0)
        self._cache[key] = entry
        self._cache.move_to_end(key)

        logger.debug("Cache put per chunk %s (size: %d)", chunk_id, len(self._cache))

    def clear(self) -> None:
        """Svuota il cache."""
        self._cache.clear()
        logger.info("Cache detector svuotato")

    def get_stats(self) -> dict:
        """Ritorna statistiche del cache."""
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "enabled": self._enabled,
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
        }


# Istanza globale del cache
_cache_instance: Optional[DetectorCache] = None


def get_detector_cache() -> DetectorCache:
    """Ritorna l'istanza singleton del cache."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = DetectorCache()
        logger.info(
            "Detector cache inizializzato (enabled: %s, max_size: %d, ttl: %ds)",
            DETECTOR_CACHE_ENABLED,
            DETECTOR_CACHE_MAX_SIZE,
            DETECTOR_CACHE_TTL_SECONDS,
        )
    return _cache_instance
