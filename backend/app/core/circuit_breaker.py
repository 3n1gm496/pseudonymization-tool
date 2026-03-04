"""
Lightweight thread-safe circuit breaker for external detectors.

State machine:
  CLOSED   — normal operation, all calls pass through
  OPEN     — failure threshold exceeded, calls are blocked (returns empty)
  HALF-OPEN — recovery timeout elapsed, one trial call is allowed

Usage:
    _CB = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

    def detect(self, chunk):
        if _CB.is_open:
            return []
        try:
            result = _do_work(chunk)
            _CB.record_success()
            return result
        except Exception as exc:
            _CB.record_failure()
            raise
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Thread-safe circuit breaker with CLOSED / OPEN / HALF-OPEN states."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0, name: str = ""):
        """
        Args:
            failure_threshold: Consecutive failures before opening.
            recovery_timeout:  Seconds to wait before allowing a trial (HALF-OPEN).
            name:              Label used in log messages.
        """
        self._threshold = failure_threshold
        self._timeout = recovery_timeout
        self._name = name or "circuit_breaker"
        self._failures = 0
        self._last_failure: float = 0.0
        self._state = "CLOSED"  # "CLOSED" | "OPEN" | "HALF-OPEN"
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        """
        Returns True if the circuit is OPEN (calls should be skipped).

        Transitions OPEN → HALF-OPEN when the recovery timeout has elapsed,
        allowing the next call to pass through as a trial.
        """
        with self._lock:
            if self._state == "OPEN":
                if time.monotonic() - self._last_failure >= self._timeout:
                    self._state = "HALF-OPEN"
                    logger.info("CircuitBreaker[%s] → HALF-OPEN (trial call allowed)", self._name)
                    return False
                return True
            return False

    def record_success(self) -> None:
        """Reset failure counter and close the circuit."""
        with self._lock:
            if self._state != "CLOSED":
                logger.info("CircuitBreaker[%s] → CLOSED (recovered)", self._name)
            self._failures = 0
            self._state = "CLOSED"

    def record_failure(self) -> None:
        """Increment failure counter; open the circuit when threshold is reached."""
        with self._lock:
            self._failures += 1
            self._last_failure = time.monotonic()
            if self._failures >= self._threshold and self._state != "OPEN":
                self._state = "OPEN"
                logger.warning(
                    "CircuitBreaker[%s] → OPEN after %d failures (retry in %.0fs)",
                    self._name,
                    self._failures,
                    self._timeout,
                )
