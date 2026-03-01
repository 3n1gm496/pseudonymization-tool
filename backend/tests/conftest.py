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
