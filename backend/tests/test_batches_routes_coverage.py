"""
Test di coverage per batches_routes.py.
Copre i path non testati: helper functions, validazione input, error paths,
endpoint lifecycle (list, get, status, findings, review, apply, delete, download).
"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.api.batches_routes import (
    _calculate_entropy,
    _sanitize_filename,
    _validate_file_magic_bytes,
    _validate_passphrase,
)
from app.core.batch_manager import create_batch, get_batch_dir, store_passphrase
from app.main import app
from app.models.schemas import (
    Batch,
    BatchConfig,
    BatchStatus,
    FileRecord,
    PresetName,
    SafetyLabel,
)

client = TestClient(app)


# ─── Helper: _sanitize_filename ───────────────────────────────────────────────

def test_sanitize_filename_normal():
    assert _sanitize_filename("report.txt") == "report.txt"


def test_sanitize_filename_path_traversal():
    result = _sanitize_filename("../../etc/passwd")
    # Slashes are replaced with underscores; the function prevents directory traversal
    # by removing path separators, even if '..' characters remain in the flat name
    assert "/" not in result
    assert "\\" not in result
    # The result should be a flat filename, not a path
    from pathlib import PurePosixPath
    assert len(PurePosixPath(result).parts) == 1


def test_sanitize_filename_leading_dots():
    result = _sanitize_filename("...hidden.txt")
    assert not result.startswith(".")


def test_sanitize_filename_empty_after_sanitize():
    # A filename that becomes empty after sanitization should get a fallback name
    result = _sanitize_filename("...")
    assert result  # not empty
    assert not result.isspace()


def test_sanitize_filename_too_long():
    long_name = "a" * 300 + ".txt"
    result = _sanitize_filename(long_name)
    assert len(result) <= 200


def test_sanitize_filename_special_chars():
    result = _sanitize_filename("file name with spaces & symbols!.txt")
    assert result.endswith(".txt")


# ─── Helper: _calculate_entropy ───────────────────────────────────────────────

def test_calculate_entropy_empty():
    assert _calculate_entropy("") == 0.0


def test_calculate_entropy_single_char():
    # Single repeated character has entropy 0
    assert _calculate_entropy("aaaa") == 0.0


def test_calculate_entropy_varied():
    # Varied string has higher entropy
    entropy = _calculate_entropy("abcdefghijklmnop")
    assert entropy > 3.0


# ─── Helper: _validate_passphrase ─────────────────────────────────────────────

def test_validate_passphrase_too_short():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        _validate_passphrase("short")
    assert exc_info.value.status_code == 400
    assert "almeno" in exc_info.value.detail


def test_validate_passphrase_low_entropy():
    from fastapi import HTTPException
    # Long but all same character → low entropy
    with pytest.raises(HTTPException) as exc_info:
        _validate_passphrase("a" * 20)
    assert exc_info.value.status_code == 400
    assert "debole" in exc_info.value.detail


def test_validate_passphrase_valid():
    # Should not raise
    _validate_passphrase("Str0ng!Passphrase#2026X")


# ─── Helper: _validate_file_magic_bytes ───────────────────────────────────────

def test_validate_magic_bytes_pdf():
    result = _validate_file_magic_bytes(b"%PDF-1.4 content", "document.pdf")
    assert result == ".pdf"


def test_validate_magic_bytes_jpg():
    result = _validate_file_magic_bytes(b"\xff\xd8\xff\xe0 jpeg data", "photo.jpg")
    assert result == ".jpg"


def test_validate_magic_bytes_png():
    result = _validate_file_magic_bytes(b"\x89PNG\r\n\x1a\n data", "image.png")
    assert result == ".png"


def test_validate_magic_bytes_txt():
    result = _validate_file_magic_bytes(b"plain text content", "notes.txt")
    assert result == ".txt"


def test_validate_magic_bytes_csv():
    result = _validate_file_magic_bytes(b"col1,col2\nval1,val2", "data.csv")
    assert result == ".csv"


def test_validate_magic_bytes_unknown_extension():
    # Unknown extension with non-matching magic bytes
    result = _validate_file_magic_bytes(b"some random bytes", "file.xyz")
    assert result is None


def test_validate_magic_bytes_mismatch_logs_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        _validate_file_magic_bytes(b"%PDF-1.4", "document.txt")
    # Should log a mismatch warning (txt declared but PDF detected)
    assert any("Mismatch" in r.message or "mismatch" in r.message.lower() for r in caplog.records)


# ─── POST /api/batches — Validation errors ────────────────────────────────────

def test_create_batch_invalid_mode():
    file_content = io.BytesIO(b"test content")
    response = client.post(
        "/api/batches",
        data={"mode": "invalid_mode", "preset": "SOC Logs", "passphrase": "Str0ng!Passphrase#2026X"},
        files={"files": ("test.txt", file_content, "text/plain")},
    )
    assert response.status_code == 400
    assert "Modalità non valida" in response.json()["detail"]


def test_create_batch_invalid_preset():
    file_content = io.BytesIO(b"test content")
    response = client.post(
        "/api/batches",
        data={"mode": "light", "preset": "NonExistentPreset999", "passphrase": "Str0ng!Passphrase#2026X"},
        files={"files": ("test.txt", file_content, "text/plain")},
    )
    assert response.status_code == 400


def test_create_batch_weak_passphrase():
    file_content = io.BytesIO(b"test content")
    response = client.post(
        "/api/batches",
        data={"mode": "light", "preset": "SOC Logs", "passphrase": "weak"},
        files={"files": ("test.txt", file_content, "text/plain")},
    )
    assert response.status_code == 400


def test_create_batch_unsupported_file_format():
    """All uploaded files have unsupported extension → 400 no valid files."""
    file_content = io.BytesIO(b"binary data")
    response = client.post(
        "/api/batches",
        data={"mode": "light", "preset": "SOC Logs", "passphrase": "Str0ng!Passphrase#2026X"},
        files={"files": ("test.exe", file_content, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Nessun file valido" in response.json()["detail"]


def test_create_batch_file_too_large():
    """File exceeds MAX_FILE_SIZE_BYTES → 400 no valid files."""
    from app.api.batches_routes import MAX_FILE_SIZE_BYTES
    oversized = io.BytesIO(b"x" * (MAX_FILE_SIZE_BYTES + 1))
    response = client.post(
        "/api/batches",
        data={"mode": "light", "preset": "SOC Logs", "passphrase": "Str0ng!Passphrase#2026X"},
        files={"files": ("big.txt", oversized, "text/plain")},
    )
    assert response.status_code == 400
    assert "Nessun file valido" in response.json()["detail"]


def test_create_batch_magic_bytes_mismatch(caplog):
    """File with .txt extension but PDF magic bytes → warning logged, file accepted.
    The code logs a warning but does NOT reject the file (permissive by design).
    """
    import logging
    pdf_magic = io.BytesIO(b"%PDF-1.4 fake pdf content here")
    with caplog.at_level(logging.WARNING):
        response = client.post(
            "/api/batches",
            data={"mode": "light", "preset": "SOC Logs", "passphrase": "Str0ng!Passphrase#2026X"},
            files={"files": ("document.txt", pdf_magic, "text/plain")},
        )
    # File is accepted (202) but a warning is logged
    assert response.status_code == 202
    assert any("Mismatch" in r.message or "mismatch" in r.message.lower() for r in caplog.records)


def test_create_batch_no_filename():
    """File with empty filename: FastAPI validates the multipart form and returns 422."""
    file_content = io.BytesIO(b"test content")
    response = client.post(
        "/api/batches",
        data={"mode": "light", "preset": "SOC Logs", "passphrase": "Str0ng!Passphrase#2026X"},
        files={"files": ("", file_content, "text/plain")},
    )
    # FastAPI returns 422 for invalid multipart form data before reaching the handler
    assert response.status_code in (400, 422)


# ─── GET /api/batches — List ──────────────────────────────────────────────────

def test_list_batches_empty():
    response = client.get("/api/batches")
    assert response.status_code == 200
    data = response.json()
    assert "batches" in data
    assert "total" in data


def test_list_batches_with_batch():
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    create_batch(batch)
    response = client.get("/api/batches")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    batch_ids = [b["batch_id"] for b in data["batches"]]
    assert batch.batch_id in batch_ids


# ─── GET /api/batches/{batch_id} — Not found ──────────────────────────────────

def test_get_batch_not_found():
    response = client.get("/api/batches/nonexistent-batch-id-xyz")
    assert response.status_code == 404


# ─── GET /api/batches/{batch_id}/status ───────────────────────────────────────

def test_get_batch_status_not_found():
    response = client.get("/api/batches/nonexistent-xyz/status")
    assert response.status_code == 404


def test_get_batch_status_no_task_id():
    """Batch without task_id returns NOT_QUEUED."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    batch.task_id = None
    create_batch(batch)
    response = client.get(f"/api/batches/{batch.batch_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["task_state"] == "NOT_QUEUED"


# ─── GET /api/batches/{batch_id}/findings ─────────────────────────────────────

def test_get_findings_not_found():
    response = client.get("/api/batches/nonexistent-xyz/findings")
    assert response.status_code == 404


def test_get_findings_empty():
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    create_batch(batch)
    response = client.get(f"/api/batches/{batch.batch_id}/findings")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["findings"] == []


# ─── POST /api/batches/{batch_id}/review ──────────────────────────────────────

def test_submit_review_not_found():
    response = client.post(
        "/api/batches/nonexistent-xyz/review",
        json={"decisions": []},
    )
    assert response.status_code == 404


def test_submit_review_wrong_status():
    """Batch in SCANNING state cannot be reviewed."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.SCANNING
    create_batch(batch)
    response = client.post(
        f"/api/batches/{batch.batch_id}/review",
        json={"decisions": []},
    )
    assert response.status_code == 400
    assert "review" in response.json()["detail"].lower()


def test_submit_review_valid():
    """Batch in REVIEW state accepts decisions."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    create_batch(batch)
    response = client.post(
        f"/api/batches/{batch.batch_id}/review",
        json={"decisions": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    assert data["total"] == 0


# ─── POST /api/batches/{batch_id}/apply ───────────────────────────────────────

def test_apply_batch_not_found():
    response = client.post("/api/batches/nonexistent-xyz/apply")
    assert response.status_code == 404


def test_apply_batch_wrong_status():
    """Batch in SCANNING state cannot be applied."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.SCANNING
    create_batch(batch)
    response = client.post(f"/api/batches/{batch.batch_id}/apply")
    assert response.status_code == 400
    assert "review" in response.json()["detail"].lower()


def test_apply_batch_missing_passphrase():
    """Batch in REVIEW state but without passphrase → 410 Gone."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    create_batch(batch)
    # Do NOT store passphrase → simulates lost passphrase
    response = client.post(f"/api/batches/{batch.batch_id}/apply")
    assert response.status_code == 410
    assert "Passphrase" in response.json()["detail"]


# ─── GET /api/batches/{batch_id}/download ─────────────────────────────────────

def test_download_not_found():
    response = client.get("/api/batches/nonexistent-xyz/download")
    assert response.status_code == 404


def test_download_text_input_batch():
    """Download ZIP is not available for text input batches."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.DONE
    batch.safety_label = SafetyLabel.SAFE_TO_UPLOAD
    batch.files = [
        FileRecord(
            original_name="input.txt",
            stored_path="/tmp/input.txt",
            is_text_input=True,
        )
    ]
    create_batch(batch)
    response = client.get(f"/api/batches/{batch.batch_id}/download")
    assert response.status_code == 400
    assert "testo" in response.json()["detail"].lower()


def test_download_batch_not_done():
    """Batch not in DONE status → 400."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    batch.safety_label = SafetyLabel.SAFE_TO_UPLOAD
    batch.files = [
        FileRecord(
            original_name="file.txt",
            stored_path="/tmp/file.txt",
            is_text_input=False,
        )
    ]
    create_batch(batch)
    response = client.get(f"/api/batches/{batch.batch_id}/download")
    assert response.status_code == 400
    assert "completato" in response.json()["detail"].lower()


def test_download_zip_not_found():
    """Batch DONE and SAFE but no ZIP file → 404."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.DONE
    batch.safety_label = SafetyLabel.SAFE_TO_UPLOAD
    batch.files = [
        FileRecord(
            original_name="file.txt",
            stored_path="/tmp/file.txt",
            is_text_input=False,
        )
    ]
    create_batch(batch)
    batch_dir = get_batch_dir(batch.batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    # No ZIP file created
    response = client.get(f"/api/batches/{batch.batch_id}/download")
    assert response.status_code == 404
    assert "ZIP" in response.json()["detail"]


def test_download_zip_success():
    """Full happy path: DONE + SAFE + ZIP exists → 200 with file."""
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.DONE
    batch.safety_label = SafetyLabel.SAFE_TO_UPLOAD
    batch.files = [
        FileRecord(
            original_name="file.txt",
            stored_path="/tmp/file.txt",
            is_text_input=False,
        )
    ]
    create_batch(batch)
    batch_dir = get_batch_dir(batch.batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    zip_path = batch_dir / "result.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("output.txt", "pseudonymized content")
    response = client.get(f"/api/batches/{batch.batch_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


# ─── DELETE /api/batches/{batch_id} ───────────────────────────────────────────

def test_delete_batch_not_found():
    response = client.delete("/api/batches/nonexistent-xyz")
    assert response.status_code == 404


def test_delete_batch_success():
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    create_batch(batch)
    response = client.delete(f"/api/batches/{batch.batch_id}")
    assert response.status_code == 200
    assert "eliminato" in response.json()["message"]


# ─── POST /api/batches/{batch_id}/passphrase/regenerate ───────────────────────

def test_regenerate_passphrase_not_found():
    response = client.post("/api/batches/nonexistent-xyz/passphrase/regenerate")
    assert response.status_code == 404


def test_regenerate_passphrase_success():
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    create_batch(batch)
    store_passphrase(batch.batch_id, "OldPassphrase!2026X")
    response = client.post(f"/api/batches/{batch.batch_id}/passphrase/regenerate")
    assert response.status_code == 200
    data = response.json()
    assert "passphrase" in data
    assert data["batch_id"] == batch.batch_id
    assert data["passphrase"] != "OldPassphrase!2026X"


# ─── GET /api/batches/{batch_id} — Full response ──────────────────────────────

def test_get_batch_full_response():
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.REVIEW
    create_batch(batch)
    response = client.get(f"/api/batches/{batch.batch_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch.batch_id
    assert "status" in data
    assert "files" in data
    assert "findings" in data
    assert "safety_label" in data


# ─── POST /api/batches — Success with auto-generated passphrase ───────────────

def test_create_batch_auto_passphrase():
    """When passphrase is empty, backend generates one automatically."""
    file_content = io.BytesIO(b"email: user@example.com")
    response = client.post(
        "/api/batches",
        data={"mode": "light", "preset": "SOC Logs", "passphrase": ""},
        files={"files": ("test.txt", file_content, "text/plain")},
    )
    assert response.status_code == 202
    data = response.json()
    assert "passphrase" in data
    assert len(data["passphrase"]) > 0


# ─── POST /api/batches — Too many files ───────────────────────────────────────

def test_create_batch_too_many_files():
    from app.api.batches_routes import MAX_UPLOAD_FILES_PER_BATCH
    files = [
        ("files", (f"file{i}.txt", io.BytesIO(b"content"), "text/plain"))
        for i in range(MAX_UPLOAD_FILES_PER_BATCH + 1)
    ]
    response = client.post(
        "/api/batches",
        data={"mode": "light", "preset": "SOC Logs", "passphrase": "Str0ng!Passphrase#2026X"},
        files=files,
    )
    assert response.status_code == 400
    assert "Massimo" in response.json()["detail"]
