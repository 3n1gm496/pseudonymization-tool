"""
Test suite for console_routes.py — coverage for uncovered paths.

Covers:
  - POST /api/console/scan: timeout, exception, invalid preset, text too long
  - POST /api/console/apply: missing fields, batch not found, timeout, exception
  - GET /api/console/{batch_id}/mapping.enc: batch not found, mapping not found, success
  - _generate_and_save_mapping: batch not found
  - _process_stored_decisions: with and without decisions
"""

import asyncio
from unittest.mock import MagicMock

import pytest
from app.api import console_routes
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


# ─── POST /api/console/scan ───────────────────────────────────────────────────


def test_console_scan_empty_text():
    """POST /api/console/scan returns 400 when text is empty."""
    response = client.post(
        "/api/console/scan",
        json={"text": "", "mode": "light", "preset": "SOC Logs"},
    )
    assert response.status_code == 400
    assert "obbligatorio" in response.json()["detail"]


def test_console_scan_text_too_long(monkeypatch):
    """POST /api/console/scan returns 400 when text exceeds max chars."""
    import app.api.console_routes as cr

    monkeypatch.setattr(cr, "MAX_CONSOLE_TEXT_CHARS", 10)
    response = client.post(
        "/api/console/scan",
        json={"text": "A" * 11, "mode": "light", "preset": "SOC Logs"},
    )
    assert response.status_code == 400
    assert "troppo lungo" in response.json()["detail"]


def test_console_scan_timeout(monkeypatch):
    """POST /api/console/scan returns 504 on asyncio.TimeoutError."""
    import app.api.console_routes as cr

    def fake_run_text_scan(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(cr, "run_text_scan", fake_run_text_scan)

    response = client.post(
        "/api/console/scan",
        json={"text": "Hello world", "mode": "light", "preset": "SOC Logs"},
    )
    assert response.status_code == 504
    assert "Timeout" in response.json()["detail"]


def test_console_scan_internal_error(monkeypatch):
    """POST /api/console/scan returns 500 on unexpected exception."""
    import app.api.console_routes as cr

    def fake_run_text_scan(*args, **kwargs):
        raise RuntimeError("unexpected error")

    monkeypatch.setattr(cr, "run_text_scan", fake_run_text_scan)

    response = client.post(
        "/api/console/scan",
        json={"text": "Hello world", "mode": "light", "preset": "SOC Logs"},
    )
    assert response.status_code == 500
    assert "Errore interno" in response.json()["detail"]
    # Must NOT leak the original error message
    assert "unexpected error" not in response.json()["detail"]


# ─── POST /api/console/apply ──────────────────────────────────────────────────


def test_console_apply_missing_batch_id():
    """POST /api/console/apply returns 400 when batch_id is missing."""
    response = client.post(
        "/api/console/apply",
        json={"file_id": "file1", "text": "Hello"},
    )
    assert response.status_code == 400
    assert "batch_id" in response.json()["detail"]


def test_console_apply_missing_file_id():
    """POST /api/console/apply returns 400 when file_id is missing."""
    response = client.post(
        "/api/console/apply",
        json={"batch_id": "batch1", "text": "Hello"},
    )
    assert response.status_code == 400
    assert "file_id" in response.json()["detail"]


def test_console_apply_text_too_long(monkeypatch):
    """POST /api/console/apply returns 400 when text exceeds max chars."""
    import app.api.console_routes as cr

    monkeypatch.setattr(cr, "MAX_CONSOLE_TEXT_CHARS", 10)
    response = client.post(
        "/api/console/apply",
        json={"batch_id": "b1", "file_id": "f1", "text": "A" * 11},
    )
    assert response.status_code == 400
    assert "troppo lungo" in response.json()["detail"]


def test_console_apply_batch_not_found(monkeypatch):
    """POST /api/console/apply returns 404 when batch does not exist."""
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: None)

    response = client.post(
        "/api/console/apply",
        json={"batch_id": "nonexistent", "file_id": "f1", "text": "Hello"},
    )
    assert response.status_code == 404
    assert "Batch non trovato" in response.json()["detail"]


def test_console_apply_timeout(monkeypatch):
    """POST /api/console/apply returns 504 on asyncio.TimeoutError."""
    import app.api.console_routes as cr

    mock_batch = MagicMock()
    monkeypatch.setattr(cr, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(cr, "_process_stored_decisions", lambda bid: None)

    def fake_run_text_apply(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(cr, "run_text_apply", fake_run_text_apply)

    response = client.post(
        "/api/console/apply",
        json={"batch_id": "b1", "file_id": "f1", "text": "Hello"},
    )
    assert response.status_code == 504
    assert "Timeout" in response.json()["detail"]


def test_console_apply_internal_error(monkeypatch):
    """POST /api/console/apply returns 500 on unexpected exception."""
    import app.api.console_routes as cr

    mock_batch = MagicMock()
    monkeypatch.setattr(cr, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(cr, "_process_stored_decisions", lambda bid: None)

    def fake_run_text_apply(*args, **kwargs):
        raise RuntimeError("unexpected error")

    monkeypatch.setattr(cr, "run_text_apply", fake_run_text_apply)

    response = client.post(
        "/api/console/apply",
        json={"batch_id": "b1", "file_id": "f1", "text": "Hello"},
    )
    assert response.status_code == 500
    assert "Errore interno" in response.json()["detail"]
    # Must NOT leak the original error message
    assert "unexpected error" not in response.json()["detail"]


# ─── GET /api/console/{batch_id}/mapping.enc ─────────────────────────────────


def test_download_console_mapping_batch_not_found(monkeypatch):
    """GET /api/console/{batch_id}/mapping.enc returns 404 when batch doesn't exist."""
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: None)

    response = client.get("/api/console/nonexistent_batch/mapping.enc")
    assert response.status_code == 404
    assert "Batch non trovato" in response.json()["detail"]


def test_download_console_mapping_file_not_found(monkeypatch, tmp_path):
    """GET /api/console/{batch_id}/mapping.enc returns 404 when mapping.enc doesn't exist."""
    mock_batch = MagicMock()
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(console_routes, "get_batch_dir", lambda bid: tmp_path)

    response = client.get("/api/console/test_batch/mapping.enc")
    assert response.status_code == 404
    assert "mapping" in response.json()["detail"].lower()


def test_download_console_mapping_success(monkeypatch, tmp_path):
    """GET /api/console/{batch_id}/mapping.enc returns file when it exists."""
    mock_batch = MagicMock()
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(console_routes, "get_batch_dir", lambda bid: tmp_path)

    # Create the mapping.enc file
    mapping_file = tmp_path / "mapping.enc"
    mapping_file.write_bytes(b"encrypted_content")

    response = client.get("/api/console/test_batch/mapping.enc")
    assert response.status_code == 200
    assert response.content == b"encrypted_content"


# ─── _process_stored_decisions ────────────────────────────────────────────────


def test_process_stored_decisions_no_decisions(monkeypatch):
    """_process_stored_decisions does nothing when no decisions stored."""
    monkeypatch.setattr(console_routes, "get_decisions", lambda bid: {})
    # Should not raise
    console_routes._process_stored_decisions("batch1")


def test_process_stored_decisions_with_decisions(monkeypatch):
    """_process_stored_decisions applies decisions when present."""
    decisions = {
        "finding_1": {"action": "ACCEPT", "custom_pseudonym": None},
        "finding_2": {"action": "REJECT", "custom_pseudonym": None},
    }
    monkeypatch.setattr(console_routes, "get_decisions", lambda bid: decisions)

    applied = []

    def fake_apply(batch_id, decision_items):
        applied.extend(decision_items)

    monkeypatch.setattr(console_routes, "apply_review_decisions", fake_apply)

    console_routes._process_stored_decisions("batch1")
    assert len(applied) == 2


def test_process_stored_decisions_invalid_action(monkeypatch):
    """_process_stored_decisions handles invalid action gracefully (defaults to ACCEPT)."""
    decisions = {
        "finding_1": {"action": "INVALID_ACTION", "custom_pseudonym": None},
    }
    monkeypatch.setattr(console_routes, "get_decisions", lambda bid: decisions)

    applied = []

    def fake_apply(batch_id, decision_items):
        applied.extend(decision_items)

    monkeypatch.setattr(console_routes, "apply_review_decisions", fake_apply)

    # Should not raise — invalid action defaults to ACCEPT
    console_routes._process_stored_decisions("batch1")
    assert len(applied) == 1
    from app.models.schemas import ReviewAction
    assert applied[0].action == ReviewAction.ACCEPT


# ─── _generate_and_save_mapping ───────────────────────────────────────────────


def test_generate_and_save_mapping_batch_not_found(monkeypatch):
    """_generate_and_save_mapping raises ValueError when batch not found."""
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: None)

    with pytest.raises(ValueError, match="Batch non trovato"):
        console_routes._generate_and_save_mapping("nonexistent", "file1", "passphrase")
