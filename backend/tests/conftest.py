"""
Pytest configuration and fixtures for pseudonymization-tool tests.
"""

import sys
from pathlib import Path

import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="session")
def test_data_dir():
    """Return path to test data directory."""
    return TEST_DATA_DIR


@pytest.fixture(scope="session")
def sample_text():
    """Sample text with sensitive data for testing."""
    return """
    Email: mario.rossi@ente.gov.it
    IP: 10.24.8.1
    Phone: +39 02 12345678
    Codice Fiscale: RSSMRA80A01H501A
    """


@pytest.fixture(scope="session")
def sample_passphrase():
    """Sample passphrase for encryption tests."""
    return "test-secure-passphrase-123456"


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration for testing."""
    monkeypatch.setenv("SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SERVER_PORT", "8000")
    monkeypatch.setenv("LOG_LEVEL", "INFO")


@pytest.fixture(scope="function")
def temp_output_dir(tmp_path):
    """Create temporary output directory for tests."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


@pytest.fixture(scope="session", autouse=True)
def setup_test_credentials():
    """
    ✅ FIX #I-006: Set test credentials for authentication tests.
    AUTH_PASSWORD must be explicitly configured (no hardcoded default).
    """
    import os

    os.environ["AUTH_PASSWORD"] = "admin123!"
    os.environ["AUTH_SECRET"] = "test-secret-key-32-chars-min-1234567890ab"
    yield


@pytest.fixture(scope="session", autouse=True)
def setup_celery_for_testing():
    """
    Configure Celery for testing mode (EAGER execution without broker).
    This executes tasks synchronously in the test process, eliminating the need
    for a running Redis broker or Celery worker.
    """
    from app.core.tasks import celery_app

    # CRITICAL: Enable EAGER mode so tasks execute synchronously
    celery_app.conf.task_always_eager = True
    # Eagerly execute tasks with no delay (no retry delays)
    celery_app.conf.task_eager_propagates = True
    yield


@pytest.fixture(scope="session", autouse=True)
def mock_redis_for_tests():
    """
    Mock Redis client for testing to avoid connection timeouts.
    Tests use in-memory session/CSRF storage with fallback.
    """
    import os

    # Use localhost with closed port for fast-fail connect (no DNS latency)
    # This triggers fallback to in-memory storage in auth.py/batch_manager.py.
    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"

    yield


@pytest.fixture(scope="function", autouse=True)
def disable_auth_for_tests(monkeypatch):
    """
    Disable authentication for all tests to avoid CSRF validation.
    Uses object.__setattr__ to bypass frozen dataclass constraint.
    """
    from app import main
    from app.core import auth

    # Use object.__setattr__ to bypass frozen dataclass constraint
    object.__setattr__(main._profile_config, "auth_enabled", False)

    # Also patch the module-level AUTH_ENABLED constant used by validate_csrf_dependency
    monkeypatch.setattr(auth, "AUTH_ENABLED", False)
    yield

    # Restore original value after test
    object.__setattr__(main._profile_config, "auth_enabled", True)
