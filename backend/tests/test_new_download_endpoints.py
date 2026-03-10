"""
Test suite per i nuovi endpoint di download introdotti nel fix Bug #4.

Copre:
  - GET /api/console/{batch_id}/download: batch non trovato, mapping mancante,
    testo mancante, successo, struttura ZIP compatibile con revert
  - GET /api/batches/{batch_id}/mapping.enc: batch non trovato, stato non completato,
    file mancante, successo
"""

import io
import zipfile
from unittest.mock import MagicMock

import pytest
from app.api import batches_routes, console_routes
from app.main import app
from app.models.schemas import BatchStatus
from fastapi.testclient import TestClient

client = TestClient(app)


# ─── GET /api/console/{batch_id}/download ────────────────────────────────────


def test_download_console_zip_batch_not_found(monkeypatch):
    """GET /api/console/{batch_id}/download returns 404 when batch doesn't exist."""
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: None)

    response = client.get("/api/console/nonexistent/download")
    assert response.status_code == 404
    assert "Batch non trovato" in response.json()["detail"]


def test_download_console_zip_mapping_missing(monkeypatch, tmp_path):
    """GET /api/console/{batch_id}/download returns 404 when mapping.enc is missing."""
    mock_batch = MagicMock()
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(console_routes, "get_batch_dir", lambda bid: tmp_path)
    # mapping.enc non esiste, pseudonymized_text.txt nemmeno

    response = client.get("/api/console/test_batch/download")
    assert response.status_code == 404
    assert "mapping" in response.json()["detail"].lower()


def test_download_console_zip_txt_missing(monkeypatch, tmp_path):
    """GET /api/console/{batch_id}/download returns 404 when pseudonymized_text.txt is missing."""
    mock_batch = MagicMock()
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(console_routes, "get_batch_dir", lambda bid: tmp_path)

    # Crea solo mapping.enc, non il txt
    (tmp_path / "mapping.enc").write_bytes(b"encrypted_mapping")

    response = client.get("/api/console/test_batch/download")
    assert response.status_code == 404
    assert "testo pseudonimizzato" in response.json()["detail"].lower()


def test_download_console_zip_success(monkeypatch, tmp_path):
    """GET /api/console/{batch_id}/download returns a valid ZIP when both files exist."""
    mock_batch = MagicMock()
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(console_routes, "get_batch_dir", lambda bid: tmp_path)

    # Crea entrambi i file
    (tmp_path / "mapping.enc").write_bytes(b"encrypted_mapping_content")
    (tmp_path / "pseudonymized_text.txt").write_text("pseudonymized text content", encoding="utf-8")

    response = client.get("/api/console/test_batch/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "pseudonymized_console_" in response.headers["content-disposition"]
    assert ".zip" in response.headers["content-disposition"]

    # Verifica che il contenuto sia un ZIP valido
    zip_content = io.BytesIO(response.content)
    assert zipfile.is_zipfile(zip_content)


def test_download_console_zip_structure_compatible_with_revert(monkeypatch, tmp_path):
    """
    Verifica che lo ZIP generato abbia la struttura corretta per la compatibilità
    con apply_revert():
    - files/<nome>.txt  → file pseudonimizzato dentro 'files/'
    - mapping.enc       → mapping cifrato nella root
    """
    mock_batch = MagicMock()
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(console_routes, "get_batch_dir", lambda bid: tmp_path)

    mapping_content = b"encrypted_mapping_data"
    txt_content = "pseudonymized text here"
    (tmp_path / "mapping.enc").write_bytes(mapping_content)
    (tmp_path / "pseudonymized_text.txt").write_text(txt_content, encoding="utf-8")

    response = client.get("/api/console/abcd1234efgh/download")
    assert response.status_code == 200

    zip_content = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_content, "r") as zf:
        names = zf.namelist()

        # mapping.enc deve essere nella root
        assert "mapping.enc" in names, f"mapping.enc non trovato nello ZIP. Contenuto: {names}"

        # Il TXT deve essere dentro files/
        txt_files = [n for n in names if n.startswith("files/") and n.endswith(".txt")]
        assert len(txt_files) == 1, f"Nessun file TXT trovato in files/. Contenuto: {names}"

        # Verifica il contenuto
        assert zf.read("mapping.enc") == mapping_content
        assert zf.read(txt_files[0]).decode("utf-8") == txt_content


def test_download_console_zip_filename_uses_batch_id(monkeypatch, tmp_path):
    """Verifica che il nome del file ZIP includa i primi 8 caratteri del batch_id."""
    mock_batch = MagicMock()
    monkeypatch.setattr(console_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(console_routes, "get_batch_dir", lambda bid: tmp_path)

    (tmp_path / "mapping.enc").write_bytes(b"enc")
    (tmp_path / "pseudonymized_text.txt").write_text("text", encoding="utf-8")

    batch_id = "abcdefgh12345678"
    response = client.get(f"/api/console/{batch_id}/download")
    assert response.status_code == 200

    disposition = response.headers["content-disposition"]
    # I primi 8 caratteri del batch_id devono essere nel nome del file
    assert batch_id[:8] in disposition


# ─── GET /api/batches/{batch_id}/mapping.enc ─────────────────────────────────


def test_download_batch_mapping_batch_not_found(monkeypatch):
    """GET /api/batches/{batch_id}/mapping.enc returns 404 when batch doesn't exist."""
    monkeypatch.setattr(batches_routes, "get_batch", lambda bid: None)

    response = client.get("/api/batches/nonexistent/mapping.enc")
    assert response.status_code == 404
    assert "Batch non trovato" in response.json()["detail"]


def test_download_batch_mapping_batch_not_completed(monkeypatch):
    """GET /api/batches/{batch_id}/mapping.enc returns 400 when batch is not in DONE state."""
    mock_batch = MagicMock()
    mock_batch.status = BatchStatus.REVIEW  # Non ancora completato
    monkeypatch.setattr(batches_routes, "get_batch", lambda bid: mock_batch)

    response = client.get("/api/batches/test_batch/mapping.enc")
    assert response.status_code == 400
    assert "non completato" in response.json()["detail"].lower()


def test_download_batch_mapping_batch_scanning_state(monkeypatch):
    """GET /api/batches/{batch_id}/mapping.enc returns 400 when batch is still scanning."""
    mock_batch = MagicMock()
    mock_batch.status = BatchStatus.SCANNING
    monkeypatch.setattr(batches_routes, "get_batch", lambda bid: mock_batch)

    response = client.get("/api/batches/test_batch/mapping.enc")
    assert response.status_code == 400


def test_download_batch_mapping_file_not_found(monkeypatch, tmp_path):
    """GET /api/batches/{batch_id}/mapping.enc returns 404 when mapping.enc file doesn't exist."""
    mock_batch = MagicMock()
    mock_batch.status = BatchStatus.DONE
    monkeypatch.setattr(batches_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(batches_routes, "get_batch_dir", lambda bid: tmp_path)
    # mapping.enc non esiste

    response = client.get("/api/batches/test_batch/mapping.enc")
    assert response.status_code == 404
    assert "mapping" in response.json()["detail"].lower()


def test_download_batch_mapping_success(monkeypatch, tmp_path):
    """GET /api/batches/{batch_id}/mapping.enc returns file when batch is DONE and file exists."""
    mock_batch = MagicMock()
    mock_batch.status = BatchStatus.DONE
    monkeypatch.setattr(batches_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(batches_routes, "get_batch_dir", lambda bid: tmp_path)

    mapping_content = b"encrypted_mapping_data_for_batch"
    (tmp_path / "mapping.enc").write_bytes(mapping_content)

    response = client.get("/api/batches/test_batch/mapping.enc")
    assert response.status_code == 200
    assert response.content == mapping_content


def test_download_batch_mapping_done_with_errors_state(monkeypatch, tmp_path):
    """GET /api/batches/{batch_id}/mapping.enc works also for DONE_WITH_ERRORS state."""
    mock_batch = MagicMock()
    mock_batch.status = BatchStatus.DONE_WITH_ERRORS
    monkeypatch.setattr(batches_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(batches_routes, "get_batch_dir", lambda bid: tmp_path)

    (tmp_path / "mapping.enc").write_bytes(b"partial_mapping")

    response = client.get("/api/batches/test_batch/mapping.enc")
    assert response.status_code == 200
    assert response.content == b"partial_mapping"


def test_download_batch_mapping_filename_uses_batch_id(monkeypatch, tmp_path):
    """Verifica che il nome del file scaricato includa i primi 8 caratteri del batch_id."""
    mock_batch = MagicMock()
    mock_batch.status = BatchStatus.DONE
    monkeypatch.setattr(batches_routes, "get_batch", lambda bid: mock_batch)
    monkeypatch.setattr(batches_routes, "get_batch_dir", lambda bid: tmp_path)

    (tmp_path / "mapping.enc").write_bytes(b"enc_data")

    batch_id = "abcdefgh12345678"
    response = client.get(f"/api/batches/{batch_id}/mapping.enc")
    assert response.status_code == 200

    # Il filename nella risposta deve contenere i primi 8 caratteri del batch_id
    disposition = response.headers.get("content-disposition", "")
    assert batch_id[:8] in disposition
