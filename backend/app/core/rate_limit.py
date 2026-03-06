"""
Rate Limiter v3 — Redis-backed with in-memory fallback

Improvements over v2 (in-memory only):
  - Redis-backed storage: rate limit state shared across multiple workers
    (required when WEB_CONCURRENCY > 1)
  - Graceful fallback: if Redis is unavailable, falls back to in-memory
    automatically (same pattern used by auth.py session management)
  - No code changes required in callers: enforce_rate_limit() API unchanged
  - Sliding window algorithm preserved (Redis ZADD/ZREMRANGEBYSCORE)

Redis key schema:
  rate_limit:{scope}:{client_ip}  → sorted set of Unix timestamps (float)
  TTL: window_seconds + 10s buffer (auto-expiry, no manual cleanup needed)

In-memory fallback (v2 behaviour):
  Used when REDIS_URL is not set or Redis is unreachable.
  Background cleanup thread runs every 60s (TTL 300s, max 5000 clients).

Configuration (via ENV):
  - REDIS_URL: Redis connection URL (e.g. redis://redis:6379/0)
    If not set, in-memory fallback is used automatically.
  - RATE_LIMIT_REQUESTS: max requests per window (default 120)
  - RATE_LIMIT_WINDOW_SECONDS: window duration (default 60s)
  - RATE_LIMIT_MAX_CLIENTS: max clients tracked in-memory (default 5000)
  - RATE_LIMIT_CLEANUP_TTL_SECONDS: bucket TTL after last request (default 300s)
  - RATE_LIMIT_CLEANUP_INTERVAL_SECONDS: cleanup thread interval (default 60s)

Usage (unchanged from v2):
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
from typing import Dict, Optional

from fastapi import HTTPException, Request

from app.core.redis_utils import safe_redis_url

logger = logging.getLogger(__name__)

# Configuration for rate limiter v3
RATE_LIMIT_MAX_CLIENTS = int(os.environ.get("RATE_LIMIT_MAX_CLIENTS", "5000"))
RATE_LIMIT_CLEANUP_TTL_SECONDS = int(os.environ.get("RATE_LIMIT_CLEANUP_TTL_SECONDS", "300"))
RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = int(os.environ.get("RATE_LIMIT_CLEANUP_INTERVAL_SECONDS", "60"))

# Redis connection retry interval (seconds): avoid hammering a down Redis
_REDIS_RETRY_INTERVAL_SECONDS = 5.0


# ─── Redis client (lazy, cached, with retry backoff) ──────────────────────────

_redis_client_cached: Optional[object] = None
_redis_last_check: float = 0.0
_redis_lock = threading.Lock()


def _get_redis_client():
    """
    Return a connected Redis client, or None if Redis is unavailable.

    Uses a dedicated lock to prevent race conditions on the cached client.
    Falls back gracefully to in-memory storage when Redis is not reachable.
    Retries at most every _REDIS_RETRY_INTERVAL_SECONDS to avoid log spam.
    """
    global _redis_client_cached, _redis_last_check

    with _redis_lock:
        now = time.time()

        # Return cached client if available
        if _redis_client_cached is not None:
            return _redis_client_cached

        # Rate-limit retry attempts to avoid hammering a down Redis
        if now - _redis_last_check < _REDIS_RETRY_INTERVAL_SECONDS:
            return None

        _redis_last_check = now
        raw_redis_url = os.environ.get("REDIS_URL")
        if not raw_redis_url:
            # No REDIS_URL configured — use in-memory fallback silently
            return None
        redis_url = safe_redis_url(raw_redis_url)

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
            logger.info(
                "rate_limit: Redis connection established (%s)",
                raw_redis_url.split("@")[-1],
            )
            return client
        except Exception as exc:
            _redis_client_cached = None
            logger.debug("rate_limit: Redis unavailable, using in-memory fallback: %s", exc)
            return None


def _reset_redis_client() -> None:
    """
    Force reset of the cached Redis client (used after connection errors).
    Thread-safe.
    """
    global _redis_client_cached, _redis_last_check
    with _redis_lock:
        _redis_client_cached = None
        _redis_last_check = 0.0


# ─── Redis-backed rate limit check ────────────────────────────────────────────


def _check_limit_redis(
    client: object,
    bucket_key: str,
    limit: int,
    window_seconds: int,
    now: float,
) -> Dict:
    """
    Sliding window rate limit check using Redis sorted sets.

    Algorithm:
      1. Remove timestamps older than (now - window_seconds)
      2. Count remaining timestamps
      3. If count >= limit → raise 429
      4. Add current timestamp with score=timestamp
      5. Set TTL on the key (auto-cleanup)

    Uses a Redis pipeline for atomicity and performance.

    Returns:
        Dict with remaining, reset, limit.

    Raises:
        HTTPException: 429 if limit exceeded.
    """
    cutoff = now - window_seconds
    redis_key = f"rate_limit:{bucket_key}"

    try:
        pipe = client.pipeline()
        # Remove expired timestamps
        pipe.zremrangebyscore(redis_key, "-inf", cutoff)
        # Count current timestamps in window
        pipe.zcard(redis_key)
        # Add current timestamp
        pipe.zadd(redis_key, {str(now): now})
        # Set TTL (window + buffer to avoid premature expiry)
        pipe.expire(redis_key, window_seconds + 10)
        results = pipe.execute()

        current_count = results[1]  # zcard result (before adding current)

        if current_count >= limit:
            # Undo the zadd we just did (we won't count this request)
            client.zrem(redis_key, str(now))
            raise HTTPException(
                status_code=429,
                detail=f"Troppe richieste per '{bucket_key.split(':')[0]}'. Riprova tra pochi secondi.",
            )

        # Get oldest timestamp for reset calculation
        oldest = client.zrange(redis_key, 0, 0, withscores=True)
        reset_time = int(oldest[0][1] + window_seconds) if oldest else int(now + window_seconds)

        return {
            "remaining": limit - current_count - 1,
            "reset": reset_time,
            "limit": limit,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("rate_limit: Redis error during check, resetting client: %s", exc)
        _reset_redis_client()
        raise  # Will be caught by caller to trigger in-memory fallback


# ─── In-memory rate limiter (v2, unchanged) ───────────────────────────────────


class RateLimiter:
    """
    Thread-safe in-memory rate limiter with automatic cleanup and memory bounds.

    Used as fallback when Redis is unavailable.

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
    ) -> Dict:
        """
        Enforce rate limit for a request. Raises HTTPException(429) if limit exceeded.
        Returns rate limit information for response headers.

        Args:
            request: FastAPI Request object (to extract client IP)
            scope: Rate limit scope (e.g., "batch_create", "console_scan")
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default 60)

        Returns:
            Dict with keys: remaining (int), reset (int Unix timestamp)

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
            remaining = limit - len(bucket["timestamps"])
            reset_time = (
                int(bucket["timestamps"][0] + window_seconds) if bucket["timestamps"] else int(now + window_seconds)
            )

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

            # Return rate limit info for response headers
            return {
                "remaining": remaining - 1,  # -1 because we just added current request
                "reset": reset_time,
                "limit": limit,
            }

    def get_stats(self) -> Dict:
        """Return rate limiter stats (for monitoring/debugging)."""
        with self._lock:
            return {
                "total_buckets": len(self._buckets),
                "max_clients": RATE_LIMIT_MAX_CLIENTS,
                "cleanup_ttl_seconds": RATE_LIMIT_CLEANUP_TTL_SECONDS,
                "cleanup_interval_seconds": RATE_LIMIT_CLEANUP_INTERVAL_SECONDS,
            }


# ─── Global Rate Limiter Instance (in-memory fallback) ────────────────────────

_rate_limiter = RateLimiter()
_rate_limiter.start_cleanup_thread()


# ─── Public API ───────────────────────────────────────────────────────────────


def enforce_rate_limit(
    request: Request,
    scope: str,
    limit: int,
    window_seconds: int = 60,
) -> Dict:
    """
    Enforce rate limit for a request.

    Uses Redis if REDIS_URL is configured and Redis is reachable.
    Falls back to in-memory rate limiter automatically if Redis is unavailable.
    The fallback is transparent to callers — the same 429 behaviour applies.

    When Redis is available, rate limit state is shared across all uvicorn
    workers (required when WEB_CONCURRENCY > 1).

    Args:
        request: FastAPI Request object
        scope: Rate limit scope (e.g., "batch_create", "console_scan")
        limit: Maximum requests allowed in window
        window_seconds: Time window in seconds (default 60)

    Returns:
        Dict with rate limit info for response headers:
        - X-RateLimit-Limit: Total limit
        - X-RateLimit-Remaining: Remaining requests in window
        - X-RateLimit-Reset: Unix timestamp when limit resets

    Raises:
        HTTPException: 429 Too Many Requests if limit exceeded

    Example:
        @router.post("/api/batches")
        async def create_batch(request: Request, ...):
            rate_info = enforce_rate_limit(request, "batch_create", limit=20)
            return JSONResponse(
                content={"message": "Created"},
                headers={
                    "X-RateLimit-Limit": str(rate_info["limit"]),
                    "X-RateLimit-Remaining": str(rate_info["remaining"]),
                    "X-RateLimit-Reset": str(rate_info["reset"]),
                }
            )
    """
    client_ip = request.client.host if request.client else "unknown"
    bucket_key = f"{scope}:{client_ip}"
    now = time.time()

    # Try Redis first
    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            return _check_limit_redis(redis_client, bucket_key, limit, window_seconds, now)
        except HTTPException:
            raise  # 429 — propagate directly
        except Exception:  # nosec B110
            # Redis error already logged in _check_limit_redis; fall through to in-memory
            pass

    # In-memory fallback
    return _rate_limiter.check_limit(request, scope, limit, window_seconds)


def get_rate_limiter_stats() -> Dict:
    """Return rate limiter stats (for monitoring endpoint)."""
    redis_client = _get_redis_client()
    stats = _rate_limiter.get_stats()
    stats["backend"] = "redis" if redis_client is not None else "in-memory"
    return stats
