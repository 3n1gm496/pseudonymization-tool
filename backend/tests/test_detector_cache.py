"""
Test per il cache dei detector results.
"""
import time
from unittest.mock import Mock

from app.detectors.cache import DetectorCache, CacheEntry
from app.detectors.base import RawFinding, EntityType
from app.parsers.base import TextChunk


def test_cache_put_and_get():
    """Test base get/put del cache."""
    cache = DetectorCache(max_size=100, ttl_seconds=60)
    
    text = "Test text con email test@example.com"
    chunk_id = "chunk_001"
    
    # Crea un chunk mock
    chunk = TextChunk(
        text=text,
        source_ref="test_source"
    )
    
    findings = [
        RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="test@example.com",
            source_chunk=chunk,
            start_pos=15,
            end_pos=32,
            confidence_score=0.9,
            detector_name="email_detector"
        )
    ]
    
    # Put
    cache.put(text, chunk_id, findings)
    
    # Get
    cached = cache.get(text, chunk_id)
    assert cached is not None
    assert len(cached) == 1
    assert cached[0].original_value == "test@example.com"


def test_cache_miss():
    """Test cache miss."""
    cache = DetectorCache(max_size=100, ttl_seconds=60)
    
    cached = cache.get("non existing text", "chunk_999")
    assert cached is None


def test_cache_ttl_expiration():
    """Test che le entry scadano dopo TTL."""
    cache = DetectorCache(max_size=100, ttl_seconds=1)  # 1 secondo TTL
    
    text = "Test text"
    chunk_id = "chunk_002"
    findings = []
    
    cache.put(text, chunk_id, findings)
    
    # Dovrebbe essere nel cache
    assert cache.get(text, chunk_id) is not None
    
    # Aspetta 2 secondi
    time.sleep(2)
    
    # Dovrebbe essere scaduto
    assert cache.get(text, chunk_id) is None


def test_cache_lru_eviction():
    """Test che il cache evicti la entry più vecchia quando è pieno."""
    cache = DetectorCache(max_size=3, ttl_seconds=60)
    
    # Riempi il cache
    cache.put("text1", "chunk1", [])
    cache.put("text2", "chunk2", [])
    cache.put("text3", "chunk3", [])
    
    # Verifica che tutto sia nel cache
    assert cache.get("text1", "chunk1") is not None
    assert cache.get("text2", "chunk2") is not None
    assert cache.get("text3", "chunk3") is not None
    
    # Aggiungi una quarta entry - dovrebbe evictare la più vecchia (text1)
    cache.put("text4", "chunk4", [])
    
    # text1 dovrebbe essere stato evitto
    assert cache.get("text1", "chunk1") is None
    # Gli altri dovrebbero esserci ancora
    assert cache.get("text2", "chunk2") is not None
    assert cache.get("text3", "chunk3") is not None
    assert cache.get("text4", "chunk4") is not None


def test_cache_lru_move_to_end():
    """Test che accedere a un'entry la muova in fondo (LRU)."""
    cache = DetectorCache(max_size=3, ttl_seconds=60)
    
    cache.put("text1", "chunk1", [])
    cache.put("text2", "chunk2", [])
    cache.put("text3", "chunk3", [])
    
    # Accedi a text1 per muoverla in fondo
    cache.get("text1", "chunk1")
    
    # Aggiungi text4 - dovrebbe evictare text2 (ora la più vecchia)
    cache.put("text4", "chunk4", [])
    
    assert cache.get("text1", "chunk1") is not None  # Ancora nel cache
    assert cache.get("text2", "chunk2") is None  # Evitto
    assert cache.get("text3", "chunk3") is not None
    assert cache.get("text4", "chunk4") is not None


def test_cache_stats():
    """Test che le stats del cache siano corrette."""
    cache = DetectorCache(max_size=100, ttl_seconds=60)
    
    # Initial stats
    stats = cache.get_stats()
    assert stats["enabled"] is True
    assert stats["size"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["hit_rate_percent"] == 0.0
    
    # Add entry
    cache.put("text1", "chunk1", [])
    
    # Miss
    cache.get("text2", "chunk2")
    
    # Hit
    cache.get("text1", "chunk1")
    
    # Check stats
    stats = cache.get_stats()
    assert stats["size"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate_percent"] == 50.0


def test_cache_clear():
    """Test che clear svuoti il cache."""
    cache = DetectorCache(max_size=100, ttl_seconds=60)
    
    cache.put("text1", "chunk1", [])
    cache.put("text2", "chunk2", [])
    
    assert cache.get_stats()["size"] == 2
    
    cache.clear()
    
    stats = cache.get_stats()
    assert stats["size"] == 0
    assert cache.get("text1", "chunk1") is None


def test_cache_disabled():
    """Test che con cache disabilitato non memorizzi nulla."""
    # Mock DETECTOR_CACHE_ENABLED=False
    import app.detectors.cache as cache_module
    original_enabled = cache_module.DETECTOR_CACHE_ENABLED
    
    try:
        cache_module.DETECTOR_CACHE_ENABLED = False
        cache = DetectorCache(max_size=100, ttl_seconds=60)
        cache._enabled = False  # Override per questo test
        
        cache.put("text1", "chunk1", [])
        
        # Non dovrebbe salvare nulla
        assert cache.get("text1", "chunk1") is None
        assert cache.get_stats()["size"] == 0
    finally:
        cache_module.DETECTOR_CACHE_ENABLED = original_enabled


def test_cache_hit_counter():
    """Test che il contatore hits per entry funzioni."""
    cache = DetectorCache(max_size=100, ttl_seconds=60)
    
    cache.put("text1", "chunk1", [])
    
    # Multiple hits
    cache.get("text1", "chunk1")
    cache.get("text1", "chunk1")
    cache.get("text1", "chunk1")
    
    # Verifica che le stats globali siano corrette
    stats = cache.get_stats()
    assert stats["hits"] == 3
    assert stats["misses"] == 0
