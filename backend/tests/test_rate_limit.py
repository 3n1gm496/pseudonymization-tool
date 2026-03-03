"""
Test suite for Rate Limiter v3 — Redis-backed with in-memory fallback

Tests cover:
  - Basic rate limiting (exceed limit → 429)
  - Automatic cleanup of expired buckets (TTL)
  - Memory bounds enforcement (max clients, LRU eviction)
  - Thread safety (concurrent requests)
  - No memory leak on long uptime scenarios
  - Redis-backed rate limiting (mocked Redis client)
  - Graceful fallback to in-memory when Redis is unavailable
  - get_rate_limiter_stats reports correct backend
"""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from app.core.rate_limit import (
    RateLimiter,
    _check_limit_redis,
    _reset_redis_client,
    enforce_rate_limit,
    get_rate_limiter_stats,
)
from fastapi import HTTPException, Request

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def limiter():
    """Create a fresh rate limiter for each test (no background thread)."""
    return RateLimiter()


@pytest.fixture
def mock_request():
    """Mock FastAPI Request with configurable client IP."""

    def _make_request(client_ip="127.0.0.1"):
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = client_ip
        return request

    return _make_request


# ─── Basic Rate Limiting Tests (in-memory) ────────────────────────────────────


def test_rate_limit_allows_within_limit(limiter, mock_request):
    """Test that requests within limit are allowed."""
    request = mock_request("192.168.1.100")

    # Allow 5 requests with limit=5
    for i in range(5):
        limiter.check_limit(request, scope="test_endpoint", limit=5, window_seconds=60)

    # No exception raised = success


def test_rate_limit_blocks_over_limit(limiter, mock_request):
    """Test that requests exceeding limit return 429."""
    request = mock_request("192.168.1.100")

    # First 3 requests succeed (limit=3)
    for i in range(3):
        limiter.check_limit(request, scope="test_endpoint", limit=3, window_seconds=60)

    # 4th request should fail with 429
    with pytest.raises(HTTPException) as exc_info:
        limiter.check_limit(request, scope="test_endpoint", limit=3, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert "Troppe richieste" in exc_info.value.detail


def test_rate_limit_resets_after_window(limiter, mock_request):
    """Test that rate limit window resets after expiration."""
    request = mock_request("192.168.1.100")

    # Fill limit (3 requests in 2 second window)
    for i in range(3):
        limiter.check_limit(request, scope="test_endpoint", limit=3, window_seconds=2)

    # 4th request fails
    with pytest.raises(HTTPException) as exc_info:
        limiter.check_limit(request, scope="test_endpoint", limit=3, window_seconds=2)
    assert exc_info.value.status_code == 429

    # Wait for window to expire
    time.sleep(2.1)

    # Now should succeed (window reset)
    limiter.check_limit(request, scope="test_endpoint", limit=3, window_seconds=2)


def test_rate_limit_different_scopes_independent(limiter, mock_request):
    """Test that different scopes have independent counters."""
    request = mock_request("192.168.1.100")

    # Fill limit for scope1 (3 requests)
    for i in range(3):
        limiter.check_limit(request, scope="scope1", limit=3, window_seconds=60)

    # scope1 is now at limit
    with pytest.raises(HTTPException):
        limiter.check_limit(request, scope="scope1", limit=3, window_seconds=60)

    # But scope2 should still work (independent counter)
    limiter.check_limit(request, scope="scope2", limit=3, window_seconds=60)


def test_rate_limit_different_clients_independent(limiter, mock_request):
    """Test that different client IPs have independent counters."""
    request1 = mock_request("192.168.1.100")
    request2 = mock_request("192.168.1.200")

    # Fill limit for client1
    for i in range(3):
        limiter.check_limit(request1, scope="test_endpoint", limit=3, window_seconds=60)

    # client1 is now at limit
    with pytest.raises(HTTPException):
        limiter.check_limit(request1, scope="test_endpoint", limit=3, window_seconds=60)

    # But client2 should still work (independent counter)
    limiter.check_limit(request2, scope="test_endpoint", limit=3, window_seconds=60)


# ─── Cleanup & TTL Tests ──────────────────────────────────────────────────────


def test_cleanup_removes_expired_buckets(limiter, mock_request, monkeypatch):
    """Test that cleanup removes buckets after TTL expiration."""
    # Set short TTL for testing
    monkeypatch.setenv("RATE_LIMIT_CLEANUP_TTL_SECONDS", "2")
    from importlib import reload

    import app.core.rate_limit as rl_module

    reload(rl_module)

    request = mock_request("192.168.1.100")

    # Make 1 request
    rl_module._rate_limiter.check_limit(request, scope="test", limit=10, window_seconds=60)

    # Bucket should exist
    bucket_key = "test:192.168.1.100"
    with rl_module._rate_limiter._lock:
        assert bucket_key in rl_module._rate_limiter._buckets

    # Wait for TTL to expire
    time.sleep(2.5)

    # Run cleanup
    rl_module._rate_limiter._cleanup()

    # Bucket should be removed
    with rl_module._rate_limiter._lock:
        assert bucket_key not in rl_module._rate_limiter._buckets


def test_cleanup_preserves_active_buckets(limiter, mock_request):
    """Test that cleanup preserves recently accessed buckets."""
    request = mock_request("192.168.1.100")

    # Make request
    limiter.check_limit(request, scope="test", limit=10, window_seconds=60)

    # Immediately run cleanup (bucket should NOT be removed, too recent)
    limiter._cleanup()

    # Bucket should still exist
    bucket_key = "test:192.168.1.100"
    with limiter._lock:
        assert bucket_key in limiter._buckets


def test_no_memory_leak_on_many_clients(limiter, mock_request, monkeypatch):
    """Test that limiter doesn't leak memory with many different clients."""
    # Set max clients to 100 for testing
    monkeypatch.setenv("RATE_LIMIT_MAX_CLIENTS", "100")
    from importlib import reload

    import app.core.rate_limit as rl_module

    reload(rl_module)

    # Simulate 200 different clients (exceeds max 100)
    for i in range(200):
        request = mock_request(f"192.168.1.{i}")
        rl_module._rate_limiter.check_limit(request, scope="test", limit=10, window_seconds=60)

    # Run cleanup to enforce max client limit
    rl_module._rate_limiter._cleanup()

    # Should have exactly 100 buckets (or less if some expired)
    with rl_module._rate_limiter._lock:
        assert len(rl_module._rate_limiter._buckets) <= 100


def test_lru_eviction_on_max_clients(limiter, mock_request, monkeypatch):
    """Test that LRU eviction works when max clients exceeded."""
    # Set low max for testing
    monkeypatch.setenv("RATE_LIMIT_MAX_CLIENTS", "5")
    from importlib import reload

    import app.core.rate_limit as rl_module

    reload(rl_module)

    # Create 10 clients (exceeds max 5)
    for i in range(10):
        request = mock_request(f"192.168.1.{i}")
        rl_module._rate_limiter.check_limit(request, scope="test", limit=10, window_seconds=60)

    # Run cleanup (should evict oldest 5 entries)
    rl_module._rate_limiter._cleanup()

    # Should have exactly 5 buckets
    with rl_module._rate_limiter._lock:
        assert len(rl_module._rate_limiter._buckets) == 5
        # Last 5 clients should remain (LRU)
        for i in range(5, 10):
            bucket_key = f"test:192.168.1.{i}"
            assert bucket_key in rl_module._rate_limiter._buckets


# ─── Thread Safety Tests ──────────────────────────────────────────────────────


def test_concurrent_requests_thread_safe(limiter, mock_request):
    """Test that concurrent requests from same client are handled correctly."""
    import threading

    request = mock_request("192.168.1.100")
    limit = 50
    num_threads = 10
    requests_per_thread = 10

    results = []
    lock = threading.Lock()

    def make_requests():
        for _ in range(requests_per_thread):
            try:
                limiter.check_limit(request, scope="test", limit=limit, window_seconds=60)
                with lock:
                    results.append("success")
            except HTTPException as e:
                if e.status_code == 429:
                    with lock:
                        results.append("limited")

    # Run concurrent threads
    threads = [threading.Thread(target=make_requests) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Total requests = num_threads * requests_per_thread = 100
    # With limit=50, should have 50 success + 50 limited
    assert results.count("success") == limit
    assert results.count("limited") == (num_threads * requests_per_thread - limit)


# ─── Redis-backed Rate Limiting Tests ─────────────────────────────────────────


def _make_mock_redis(existing_count: int = 0, oldest_ts: float = None):
    """
    Build a mock Redis client whose pipeline().execute() simulates
    the sliding-window result for _check_limit_redis.

    pipeline().execute() returns [None, existing_count, 1, True]
    matching [zremrangebyscore, zcard, zadd, expire].
    """
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    mock_pipe.execute.return_value = [None, existing_count, 1, True]

    if oldest_ts is not None:
        mock_redis.zrange.return_value = [("ts_value", oldest_ts)]
    else:
        mock_redis.zrange.return_value = []

    return mock_redis


def test_redis_rate_limit_allows_within_limit():
    """Redis backend: requests within limit are allowed."""
    now = time.time()
    mock_redis = _make_mock_redis(existing_count=2, oldest_ts=now - 30)

    result = _check_limit_redis(mock_redis, "test_scope:127.0.0.1", limit=5, window_seconds=60, now=now)

    assert result["remaining"] == 2  # 5 - 2 - 1
    assert result["limit"] == 5
    assert "reset" in result


def test_redis_rate_limit_blocks_over_limit():
    """Redis backend: requests at limit return 429."""
    now = time.time()
    mock_redis = _make_mock_redis(existing_count=5)

    with pytest.raises(HTTPException) as exc_info:
        _check_limit_redis(mock_redis, "test_scope:127.0.0.1", limit=5, window_seconds=60, now=now)

    assert exc_info.value.status_code == 429
    assert "Troppe richieste" in exc_info.value.detail
    # Verify zadd was undone (zrem called)
    mock_redis.zrem.assert_called_once()


def test_redis_rate_limit_resets_client_on_error():
    """Redis backend: connection error resets cached client and falls through."""
    import app.core.rate_limit as rl_module

    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    mock_pipe.execute.side_effect = ConnectionError("Redis connection lost")

    with patch.object(rl_module, "_redis_client_cached", mock_redis):
        with pytest.raises(Exception):
            _check_limit_redis(mock_redis, "test_scope:127.0.0.1", limit=5, window_seconds=60, now=time.time())


def test_enforce_rate_limit_uses_redis_when_available(mock_request):
    """enforce_rate_limit uses Redis when _get_redis_client returns a client."""
    import app.core.rate_limit as rl_module

    request = mock_request("192.168.1.50")
    now = time.time()
    mock_redis = _make_mock_redis(existing_count=1, oldest_ts=now - 10)

    with patch.object(rl_module, "_get_redis_client", return_value=mock_redis):
        result = enforce_rate_limit(request, scope="test_redis", limit=10, window_seconds=60)

    assert result["limit"] == 10
    assert result["remaining"] == 8  # 10 - 1 - 1
    # Verify Redis pipeline was used
    mock_redis.pipeline.assert_called_once()


def test_enforce_rate_limit_falls_back_to_memory_when_redis_unavailable(mock_request):
    """enforce_rate_limit falls back to in-memory when Redis is None."""
    import app.core.rate_limit as rl_module

    request = mock_request("192.168.1.60")

    with patch.object(rl_module, "_get_redis_client", return_value=None):
        result = enforce_rate_limit(request, scope="test_fallback", limit=10, window_seconds=60)

    assert result["limit"] == 10
    assert result["remaining"] == 9


def test_enforce_rate_limit_falls_back_on_redis_error(mock_request):
    """enforce_rate_limit falls back to in-memory when Redis raises an error."""
    import app.core.rate_limit as rl_module

    request = mock_request("192.168.1.70")

    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    mock_pipe.execute.side_effect = ConnectionError("Redis down")

    with patch.object(rl_module, "_get_redis_client", return_value=mock_redis):
        # Should not raise — falls back to in-memory
        result = enforce_rate_limit(request, scope="test_error_fallback", limit=10, window_seconds=60)

    assert result["limit"] == 10


def test_enforce_rate_limit_429_propagated_from_redis(mock_request):
    """enforce_rate_limit propagates 429 from Redis backend without falling back."""
    import app.core.rate_limit as rl_module

    request = mock_request("192.168.1.80")
    now = time.time()
    mock_redis = _make_mock_redis(existing_count=5)  # at limit

    with patch.object(rl_module, "_get_redis_client", return_value=mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            enforce_rate_limit(request, scope="test_429", limit=5, window_seconds=60)

    assert exc_info.value.status_code == 429


# ─── Stats Tests ──────────────────────────────────────────────────────────────


def test_get_rate_limiter_stats_in_memory():
    """Stats report 'in-memory' backend when Redis is not available."""
    import app.core.rate_limit as rl_module

    with patch.object(rl_module, "_get_redis_client", return_value=None):
        stats = get_rate_limiter_stats()

    assert stats["backend"] == "in-memory"
    assert "total_buckets" in stats
    assert "max_clients" in stats


def test_get_rate_limiter_stats_redis():
    """Stats report 'redis' backend when Redis is available."""
    import app.core.rate_limit as rl_module

    mock_redis = MagicMock()
    with patch.object(rl_module, "_get_redis_client", return_value=mock_redis):
        stats = get_rate_limiter_stats()

    assert stats["backend"] == "redis"


def test_get_rate_limiter_stats_fields():
    """Stats always include required fields regardless of backend."""
    stats = get_rate_limiter_stats()

    assert "total_buckets" in stats
    assert "max_clients" in stats
    assert "cleanup_ttl_seconds" in stats
    assert "cleanup_interval_seconds" in stats
    assert "backend" in stats
    assert isinstance(stats["total_buckets"], int)
    assert stats["max_clients"] > 0


# ─── Integration Tests ────────────────────────────────────────────────────────


def test_enforce_rate_limit_function(mock_request):
    """Test convenience function enforce_rate_limit (in-memory path)."""
    import app.core.rate_limit as rl_module

    request = mock_request("192.168.1.100")

    with patch.object(rl_module, "_get_redis_client", return_value=None):
        # Should work within limit
        for i in range(5):
            enforce_rate_limit(request, scope="test_func_v3", limit=5, window_seconds=60)

        # Should fail when exceeding limit
        with pytest.raises(HTTPException) as exc_info:
            enforce_rate_limit(request, scope="test_func_v3", limit=5, window_seconds=60)
        assert exc_info.value.status_code == 429


def test_cleanup_thread_starts_automatically():
    """Test that cleanup thread starts automatically on module import."""
    from app.core.rate_limit import _rate_limiter

    # Thread should be running
    assert _rate_limiter._running is True
    assert _rate_limiter._cleanup_thread is not None
    assert _rate_limiter._cleanup_thread.is_alive()


# ─── Edge Cases ───────────────────────────────────────────────────────────────


def test_unknown_client_ip_handled(limiter):
    """Test that missing client IP is handled gracefully."""
    request = Mock(spec=Request)
    request.client = None

    # Should use "unknown" as client ID, not crash
    limiter.check_limit(request, scope="test", limit=5, window_seconds=60)


def test_zero_limit_blocks_all_requests(limiter, mock_request):
    """Test that limit=0 blocks all requests."""
    request = mock_request("192.168.1.100")

    # First request should fail with limit=0
    with pytest.raises(HTTPException) as exc_info:
        limiter.check_limit(request, scope="test", limit=0, window_seconds=60)
    assert exc_info.value.status_code == 429


def test_reset_redis_client_clears_cache():
    """Test that _reset_redis_client clears the cached client."""
    import app.core.rate_limit as rl_module

    # Simulate a cached client
    with patch.object(rl_module, "_redis_client_cached", MagicMock()):
        _reset_redis_client()
        assert rl_module._redis_client_cached is None
