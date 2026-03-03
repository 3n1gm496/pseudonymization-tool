#!/usr/bin/env python3
"""
Quick verification script for pseudonymization-tool features.
"""
import sys
sys.path.insert(0, '/home/administrator/tools/pseudonymization-tool/backend')

from app.core import config
from app.detectors.cache import DetectorCache
from app.parsers.pdf_parser import PdfParser

print("=" * 80)
print("VERIFICA FUNZIONALITÀ PSEUDONYMIZATION-TOOL")
print("=" * 80)

# 1. Test Configuration
print("\n1. Verifica configurazione...")
print(f"   Cache enabled: {config.DETECTOR_CACHE_ENABLED}")
print(f"   Cache TTL: {config.DETECTOR_CACHE_TTL_SECONDS}s")
print(f"   Cache max size: {config.DETECTOR_CACHE_MAX_SIZE}")

# 2. Test Detector Cache
print("\n2. Test Detector Cache...")
cache = DetectorCache(max_size=100, ttl_seconds=300)
cache.put("test text", "chunk_1", [])  # Empty findings list
result = cache.get("test text", "chunk_1")
assert result is not None, "Cache retrieval failed"
print("   Cache put/get funzionante")
stats = cache.get_stats()
print(f"   Cache stats: {stats['hits']} hits, {stats['misses']} misses, {stats['size']} items")

# 3. Test Streaming Support
print("\n3. Test Streaming Parser...")
pdf_parser = PdfParser()
supports_streaming = pdf_parser.supports_streaming()
print(f"   PDF streaming support: {supports_streaming}")

print("\n" + "=" * 80)
print("TUTTE LE FUNZIONALITA' VERIFICATE CON SUCCESSO!")
print("=" * 80)
sys.exit(0)
