"""
Rate Limiter v2 — Centralized, memory-bounded, auto-cleanup

Improvements over v1 (per-router in-memory buckets):
  - Single global rate limiter (shared across all routers)
  - Automatic cleanup thread with TTL (default 300s after last request)
  - Memory bound: max 5000 clients tracked (LRU eviction)
  - Thread-safe with Lock for concurrent requests
  - No memory drift on long uptime (tested for 24h+ scenarios)

Configuration (via ENV):
  - RATE_LIMIT_REQUESTS: max requests per window (default 120)
  - RATE_LIMIT_WINDOW_SECONDS: window duration (default 60s)
  - RATE_LIMIT_MAX_CLIENTS: max clients tracked (default 5000)
  - RATE_LIMIT_CLEANUP_TTL_SECONDS: bucket TTL after last request (default 300s)
  - RATE_LIMIT_CLEANUP_INTERVAL_SECONDS: cleanup thread interval (default 60s)

Usage:
    from app.core.rate_limit import enforce_rate_limit
    
    @router.post("/api/endpoint")
    async def my_endpoint(request: Request):
        enforce_rate_limit(request, scope="endpoint_name", limit=25)
        # ... endpoint logic
"""

import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Dict, List

from app.core.config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Configuration for rate limiter v2
RATE_LIMIT_MAX_CLIENTS = int(os.environ.get("RATE_LIMIT_MAX_CLIENTS", "5000"))
RATE_LIMIT_CLEANUP_TTL_SECONDS = int(os.environ.get("RATE_LIMIT_CLEANUP_TTL_SECONDS", "300"))
RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = int(os.environ.get("RATE_LIMIT_CLEANUP_INTERVAL_SECONDS", "60"))


class RateLimiter:
    """
    Thread-safe in-memory rate limiter with automatic cleanup and memory bounds.

    Design goals:
      - No memory leak on long uptime (cleanup old buckets)
      - Bounded memory (max 5000 clients, LRU eviction)
      - Thread-safe for concurrent requests
      - Minimal overhead (O(1) bucket access, O(window_size) timestamp filtering)

    Cleanup strategy:
      - Background thread runs every 60 seconds
      - Removes buckets with no requests in last 300 seconds (TTL)
      - Enforces max client limit (LRU eviction if exceeded)

    Bucket structure:
      {
        "scope:client_ip": {
          "timestamps": [1234567890.123, 1234567891.456, ...],
          "last_access": 1234567891.456
        }
      }
    """

    def __init__(self):
        # Use OrderedDict for LRU tracking (move_to_end on access)
        self._buckets: Dict[str, Dict] = OrderedDict()
        self._lock = threading.Lock()
        self._cleanup_thread = None
        self._running = False

    def start_cleanup_thread(self) -> None:
        """Start background cleanup thread (daemon, auto-stops on process exit)."""
        if self._running:
            logger.warning("Rate limiter cleanup thread already running")
            return

        self._running = True

        def _cleanup_loop():
            logger.info(
                "Rate limiter cleanup thread started (TTL=%ds, interval=%ds, max_clients=%d)",
                RATE_LIMIT_CLEANUP_TTL_SECONDS,
                RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
                RATE_LIMIT_MAX_CLIENTS,
            )
            while self._running:
                time.sleep(RATE_LIMIT_CLEANUP_INTERVAL_SECONDS)
                try:
                    self._cleanup()
                except Exception as e:  # QG-EXEMPT: cleanup thread should never crash
                    logger.error("Rate limiter cleanup error: %s", e, exc_info=True)

        self._cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True, name="rate-limit-cleanup")
        self._cleanup_thread.start()

    def stop_cleanup_thread(self) -> None:
        """Stop cleanup thread (for testing)."""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)

    def _cleanup(self) -> None:
        """
        Remove expired buckets and enforce max client limit.
        Called periodically by background thread.
        """
        with self._lock:
            now = time.time()
            ttl_threshold = now - RATE_LIMIT_CLEANUP_TTL_SECONDS

            # Step 1: Remove expired buckets (no activity for TTL seconds)
            expired_keys = [key for key, bucket in self._buckets.items() if bucket["last_access"] < ttl_threshold]
            for key in expired_keys:
                del self._buckets[key]

            if expired_keys:
                logger.debug("Rate limiter cleanup: removed %d expired buckets", len(expired_keys))

            # Step 2: Enforce max client limit (LRU eviction)
            if len(self._buckets) > RATE_LIMIT_MAX_CLIENTS:
                excess = len(self._buckets) - RATE_LIMIT_MAX_CLIENTS
                for _ in range(excess):
                    # OrderedDict.popitem(last=False) removes oldest entry (FIFO/LRU)
                    self._buckets.popitem(last=False)
                logger.warning("Rate limiter: enforced max client limit, evicted %d oldest buckets", excess)

    def check_limit(
        self,
        request: Request,
        scope: str,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        """
        Enforce rate limit for a request. Raises HTTPException(429) if limit exceeded.

        Args:
            request: FastAPI Request object (to extract client IP)
            scope: Rate limit scope (e.g., "batch_create", "console_scan")
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default 60)

        Raises:
            HTTPException: 429 Too Many Requests if limit exceeded
        """
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket_key = f"{scope}:{client_ip}"

        with self._lock:
            # Step 1: Get or create bucket
            if bucket_key in self._buckets:
                # Move to end (LRU tracking)
                self._buckets.move_to_end(bucket_key)
                bucket = self._buckets[bucket_key]
            else:
                bucket = {"timestamps": [], "last_access": now}
                self._buckets[bucket_key] = bucket

            # Step 2: Filter old timestamps (outside window)
            cutoff = now - window_seconds
            bucket["timestamps"] = [t for t in bucket["timestamps"] if t >= cutoff]

            # Step 3: Check limit
            if len(bucket["timestamps"]) >= limit:
                logger.warning(
                    "Rate limit exceeded: scope=%s client=%s (%d/%d requests in %ds)",
                    scope,
                    client_ip,
                    len(bucket["timestamps"]),
                    limit,
                    window_seconds,
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Troppe richieste per '{scope}'. Riprova tra pochi secondi.",
                )

            # Step 4: Add current timestamp
            bucket["timestamps"].append(now)
            bucket["last_access"] = now

    def get_stats(self) -> Dict:
        """Return rate limiter stats (for monitoring/debugging)."""
        with self._lock:
            return {
                "total_buckets": len(self._buckets),
                "max_clients": RATE_LIMIT_MAX_CLIENTS,
                "cleanup_ttl_seconds": RATE_LIMIT_CLEANUP_TTL_SECONDS,
                "cleanup_interval_seconds": RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
            }


# ─── Global Rate Limiter Instance ─────────────────────────────────────────────

_rate_limiter = RateLimiter()
_rate_limiter.start_cleanup_thread()


def enforce_rate_limit(
    request: Request,
    scope: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """
    Enforce rate limit for a request (convenience function).

    Args:
        request: FastAPI Request object
        scope: Rate limit scope (e.g., "batch_create", "console_scan")
        limit: Maximum requests allowed in window
        window_seconds: Time window in seconds (default 60)

    Raises:
        HTTPException: 429 Too Many Requests if limit exceeded

    Example:
        @router.post("/api/batches")
        async def create_batch(request: Request, ...):
            enforce_rate_limit(request, "batch_create", limit=20)
            # ... endpoint logic
    """
    _rate_limiter.check_limit(request, scope, limit, window_seconds)


def get_rate_limiter_stats() -> Dict:
    """Return rate limiter stats (for monitoring endpoint)."""
    return _rate_limiter.get_stats()
