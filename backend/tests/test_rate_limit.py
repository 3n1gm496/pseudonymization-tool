"""
Test suite for Rate Limiter v2 — P2-3 Robustness Improvements

Tests cover:
  - Basic rate limiting (exceed limit → 429)
  - Automatic cleanup of expired buckets (TTL)
  - Memory bounds enforcement (max clients, LRU eviction)
  - Thread safety (concurrent requests)
  - No memory leak on long uptime scenarios
"""

import time
from unittest.mock import Mock

import pytest
from app.core.rate_limit import RateLimiter, enforce_rate_limit, get_rate_limiter_stats
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


# ─── Basic Rate Limiting Tests ───────────────────────────────────────────────


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


# ─── Integration Tests ────────────────────────────────────────────────────────


def test_enforce_rate_limit_function(mock_request):
    """Test convenience function enforce_rate_limit."""
    request = mock_request("192.168.1.100")

    # Should work within limit
    for i in range(5):
        enforce_rate_limit(request, scope="test_func", limit=5, window_seconds=60)

    # Should fail when exceeding limit
    with pytest.raises(HTTPException) as exc_info:
        enforce_rate_limit(request, scope="test_func", limit=5, window_seconds=60)
    assert exc_info.value.status_code == 429


def test_get_rate_limiter_stats():
    """Test stats reporting function."""
    stats = get_rate_limiter_stats()

    assert "total_buckets" in stats
    assert "max_clients" in stats
    assert "cleanup_ttl_seconds" in stats
    assert "cleanup_interval_seconds" in stats
    assert isinstance(stats["total_buckets"], int)
    assert stats["max_clients"] > 0


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
