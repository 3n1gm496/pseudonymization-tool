"""
Test unitari per app.detectors.cache — DetectorCache LRU con TTL.
Coverage target: 100%
"""

import time
from unittest.mock import patch

import pytest
from app.detectors.base import EntityType, RawFinding
from app.detectors.cache import CacheEntry, DetectorCache, get_detector_cache
from app.parsers.base import TextChunk

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def cache():
    """Cache con dimensione e TTL ridotti per i test."""
    return DetectorCache(max_size=3, ttl_seconds=60)


@pytest.fixture
def sample_findings():
    """Lista di RawFinding di esempio."""
    chunk = TextChunk(text="mario@example.com", source_ref="riga 1", line_number=1)
    return [
        RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="mario@example.com",
            source_chunk=chunk,
            confidence_score=0.99,
            detector_name="regex_email",
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Test: CacheEntry
# ─────────────────────────────────────────────────────────────────────────────


def test_cache_entry_defaults():
    """CacheEntry ha hits=0 per default."""
    entry = CacheEntry(findings=[], timestamp=time.time())
    assert entry.hits == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: DetectorCache — abilitato
# ─────────────────────────────────────────────────────────────────────────────


def test_cache_miss_on_empty(cache, sample_findings):
    """Cache vuota restituisce None (miss)."""
    result = cache.get("testo qualsiasi", "chunk-001")
    assert result is None


def test_cache_put_and_get(cache, sample_findings):
    """put() seguito da get() restituisce i findings corretti."""
    cache.put("testo", "chunk-001", sample_findings)
    result = cache.get("testo", "chunk-001")
    assert result == sample_findings


def test_cache_hit_increments_counters(cache, sample_findings):
    """get() su cache hit incrementa _hits e entry.hits."""
    cache.put("testo", "chunk-001", sample_findings)
    cache.get("testo", "chunk-001")
    cache.get("testo", "chunk-001")
    stats = cache.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 0


def test_cache_miss_increments_misses(cache):
    """get() su cache miss incrementa _misses."""
    cache.get("non esiste", "chunk-999")
    stats = cache.get_stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0


def test_cache_key_is_chunk_and_text_specific(cache, sample_findings):
    """Chiavi diverse per stesso testo con chunk_id diverso."""
    cache.put("testo", "chunk-A", sample_findings)
    assert cache.get("testo", "chunk-B") is None
    assert cache.get("testo", "chunk-A") == sample_findings


def test_cache_lru_eviction(cache, sample_findings):
    """Quando il cache è pieno, l'elemento LRU viene rimosso."""
    cache.put("t1", "c1", sample_findings)
    cache.put("t2", "c2", sample_findings)
    cache.put("t3", "c3", sample_findings)
    # c1 è il più vecchio (LRU) — viene evicted quando aggiungiamo c4
    cache.put("t4", "c4", sample_findings)
    assert cache.get("t1", "c1") is None  # evicted
    assert cache.get("t2", "c2") == sample_findings
    assert cache.get("t3", "c3") == sample_findings
    assert cache.get("t4", "c4") == sample_findings


def test_cache_lru_access_updates_order(cache, sample_findings):
    """Un accesso sposta l'entry in fondo, proteggendola dall'eviction."""
    cache.put("t1", "c1", sample_findings)
    cache.put("t2", "c2", sample_findings)
    cache.put("t3", "c3", sample_findings)
    # Accediamo a c1 — ora è il più recente
    cache.get("t1", "c1")
    # Aggiungiamo c4 — c2 è ora il LRU e viene evicted
    cache.put("t4", "c4", sample_findings)
    assert cache.get("t1", "c1") == sample_findings  # protetto dall'accesso
    assert cache.get("t2", "c2") is None  # evicted


def test_cache_ttl_expiry(sample_findings):
    """Entry scaduta viene rimossa e restituisce None."""
    cache = DetectorCache(max_size=10, ttl_seconds=1)
    cache.put("testo", "chunk-001", sample_findings)
    # Simula il passaggio del tempo
    with patch("app.detectors.cache.time") as mock_time:
        mock_time.time.return_value = time.time() + 120  # 2 minuti dopo
        result = cache.get("testo", "chunk-001")
    assert result is None


def test_cache_update_existing_key(cache, sample_findings):
    """put() su chiave esistente aggiorna l'entry senza aumentare la dimensione."""
    cache.put("testo", "chunk-001", sample_findings)
    new_findings = []
    cache.put("testo", "chunk-001", new_findings)
    assert cache.get("testo", "chunk-001") == new_findings
    assert cache.get_stats()["size"] == 1


def test_cache_clear(cache, sample_findings):
    """clear() svuota il cache."""
    cache.put("t1", "c1", sample_findings)
    cache.put("t2", "c2", sample_findings)
    cache.clear()
    assert cache.get_stats()["size"] == 0
    assert cache.get("t1", "c1") is None


def test_cache_get_stats_hit_rate(cache, sample_findings):
    """get_stats() calcola correttamente hit_rate_percent."""
    cache.put("testo", "chunk-001", sample_findings)
    cache.get("testo", "chunk-001")  # hit
    cache.get("non esiste", "chunk-999")  # miss
    stats = cache.get_stats()
    assert stats["hit_rate_percent"] == 50.0
    assert stats["size"] == 1
    assert stats["max_size"] == 3
    assert stats["ttl_seconds"] == 60


def test_cache_get_stats_no_requests(cache):
    """get_stats() con 0 richieste non divide per zero."""
    stats = cache.get_stats()
    assert stats["hit_rate_percent"] == 0.0
    assert stats["hits"] == 0
    assert stats["misses"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: DetectorCache — disabilitato
# ─────────────────────────────────────────────────────────────────────────────


def test_cache_disabled_get_returns_none(sample_findings):
    """Cache disabilitato: get() restituisce sempre None."""
    cache = DetectorCache(max_size=10, ttl_seconds=60)
    cache._enabled = False
    cache.put("testo", "chunk-001", sample_findings)
    assert cache.get("testo", "chunk-001") is None


def test_cache_disabled_put_is_noop(sample_findings):
    """Cache disabilitato: put() non aggiunge nulla."""
    cache = DetectorCache(max_size=10, ttl_seconds=60)
    cache._enabled = False
    cache.put("testo", "chunk-001", sample_findings)
    assert cache.get_stats()["size"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_detector_cache singleton
# ─────────────────────────────────────────────────────────────────────────────


def test_get_detector_cache_returns_singleton():
    """get_detector_cache() restituisce sempre la stessa istanza."""
    import app.detectors.cache as cache_module

    # Reset singleton per test isolato
    cache_module._cache_instance = None
    c1 = get_detector_cache()
    c2 = get_detector_cache()
    assert c1 is c2


def test_get_detector_cache_is_detector_cache_instance():
    """get_detector_cache() restituisce un'istanza di DetectorCache."""
    import app.detectors.cache as cache_module

    cache_module._cache_instance = None
    instance = get_detector_cache()
    assert isinstance(instance, DetectorCache)
