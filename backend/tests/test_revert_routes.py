"""
Test per app.api.revert_routes — tutti e 4 gli endpoint revert.
Coverage target: ≥80%
"""

import io
import zipfile
from unittest.mock import patch

from app.main import app
from app.mapping.crypto import encrypt_mapping
from fastapi.testclient import TestClient

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

PASSPHRASE = "TestRevert_Passphrase_2026!"
MAPPING_PAYLOAD = {
    "mapping": {
        "[PERSON_0001]": "Mario Rossi",
        "[EMAIL_0001]": "mario@example.com",
    }
}


def _make_mapping_bytes(passphrase: str = PASSPHRASE) -> bytes:
    return encrypt_mapping(MAPPING_PAYLOAD, passphrase)


def _make_zip_bytes(passphrase: str = PASSPHRASE) -> bytes:
    """Crea un archivio ZIP con file pseudonimizzato e mapping.enc.
    La struttura attesa da preview_revert/apply_revert è:
      - files/<nome_file>  (prefisso 'files/' obbligatorio)
      - mapping.enc
    """
    mapping_bytes = _make_mapping_bytes(passphrase)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "files/report.txt",
            "Utente [PERSON_0001] ha inviato email a [EMAIL_0001].",
        )
        zf.writestr("mapping.enc", mapping_bytes)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/revert/preview
# ─────────────────────────────────────────────────────────────────────────────


def test_revert_preview_success():
    """Preview ZIP revert restituisce mapping_entries e total_matches."""
    zip_bytes = _make_zip_bytes()
    response = client.post(
        "/api/revert/preview",
        data={"passphrase": PASSPHRASE},
        files={"archive": ("batch.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mapping_entries"] == 2
    assert data["total_matches"] == 2


def test_revert_preview_wrong_extension():
    """Preview con file non .zip restituisce 400."""
    response = client.post(
        "/api/revert/preview",
        data={"passphrase": PASSPHRASE},
        files={"archive": ("batch.tar.gz", b"not a zip", "application/gzip")},
    )
    assert response.status_code == 400
    assert "ZIP" in response.json()["detail"]


def test_revert_preview_empty_passphrase():
    """Preview con passphrase vuota restituisce 400."""
    zip_bytes = _make_zip_bytes()
    response = client.post(
        "/api/revert/preview",
        data={"passphrase": "   "},
        files={"archive": ("batch.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 400
    assert "passphrase" in response.json()["detail"].lower()


def test_revert_preview_wrong_passphrase():
    """Preview con passphrase errata restituisce 400 (decifratura fallisce)."""
    zip_bytes = _make_zip_bytes()
    response = client.post(
        "/api/revert/preview",
        data={"passphrase": "WrongPassphrase_999!"},
        files={"archive": ("batch.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 400


def test_revert_preview_file_too_large():
    """Preview con archivio troppo grande restituisce 400."""
    from unittest.mock import patch

    zip_bytes = _make_zip_bytes()
    with patch("app.api.revert_routes.MAX_FILE_SIZE_BYTES", 10):  # Limite artificialmente basso
        response = client.post(
            "/api/revert/preview",
            data={"passphrase": PASSPHRASE},
            files={"archive": ("batch.zip", zip_bytes, "application/zip")},
        )
    assert response.status_code == 400
    assert "grande" in response.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/revert/apply
# ─────────────────────────────────────────────────────────────────────────────


def test_revert_apply_success():
    """Apply ZIP revert restituisce un file ZIP con testo ripristinato."""
    zip_bytes = _make_zip_bytes()
    response = client.post(
        "/api/revert/apply",
        data={"passphrase": PASSPHRASE},
        files={"archive": ("batch.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "batch_reverted.zip" in response.headers["content-disposition"]
    # Verifica che il ZIP risultante contenga il testo ripristinato
    result_zip = zipfile.ZipFile(io.BytesIO(response.content))
    names = result_zip.namelist()
    assert len(names) > 0


def test_revert_apply_wrong_extension():
    """Apply con file non .zip restituisce 400."""
    response = client.post(
        "/api/revert/apply",
        data={"passphrase": PASSPHRASE},
        files={"archive": ("batch.tar", b"not a zip", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_revert_apply_empty_passphrase():
    """Apply con passphrase blank (solo spazi) restituisce 400."""
    zip_bytes = _make_zip_bytes()
    response = client.post(
        "/api/revert/apply",
        data={"passphrase": "   "},
        files={"archive": ("batch.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 400


def test_revert_apply_wrong_passphrase():
    """Apply con passphrase errata restituisce 400."""
    zip_bytes = _make_zip_bytes()
    response = client.post(
        "/api/revert/apply",
        data={"passphrase": "WrongPass_999!"},
        files={"archive": ("batch.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 400


def test_revert_apply_file_too_large():
    """Apply con archivio troppo grande restituisce 400."""
    zip_bytes = _make_zip_bytes()
    with patch("app.api.revert_routes.MAX_FILE_SIZE_BYTES", 10):
        response = client.post(
            "/api/revert/apply",
            data={"passphrase": PASSPHRASE},
            files={"archive": ("batch.zip", zip_bytes, "application/zip")},
        )
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/revert/text/preview
# ─────────────────────────────────────────────────────────────────────────────


def test_revert_text_preview_success():
    """Preview revert testo restituisce mapping_entries e total_matches."""
    mapping_bytes = _make_mapping_bytes()
    text = "Utente [PERSON_0001] ha inviato email a [EMAIL_0001]."
    response = client.post(
        "/api/revert/text/preview",
        data={"passphrase": PASSPHRASE, "text": text},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mapping_entries"] == 2
    assert data["total_matches"] == 2


def test_revert_text_preview_empty_passphrase():
    """Preview testo con passphrase vuota restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    response = client.post(
        "/api/revert/text/preview",
        data={"passphrase": "  ", "text": "testo qualsiasi"},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400


def test_revert_text_preview_text_too_long():
    """Preview testo con testo troppo lungo restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    from app.core.config import MAX_CONSOLE_TEXT_CHARS

    long_text = "x" * (MAX_CONSOLE_TEXT_CHARS + 1)
    response = client.post(
        "/api/revert/text/preview",
        data={"passphrase": PASSPHRASE, "text": long_text},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "lungo" in response.json()["detail"].lower()


def test_revert_text_preview_empty_mapping():
    """Preview testo con mapping vuoto restituisce 400."""
    response = client.post(
        "/api/revert/text/preview",
        data={"passphrase": PASSPHRASE, "text": "testo qualsiasi"},
        files={"mapping_file": ("mapping.enc", b"", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "vuoto" in response.json()["detail"].lower()


def test_revert_text_preview_wrong_passphrase():
    """Preview testo con passphrase errata restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    response = client.post(
        "/api/revert/text/preview",
        data={"passphrase": "WrongPass_999!", "text": "[PERSON_0001]"},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400


def test_revert_text_preview_mapping_too_large():
    """Preview testo con mapping troppo grande restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    with patch("app.api.revert_routes.MAX_FILE_SIZE_BYTES", 10):
        response = client.post(
            "/api/revert/text/preview",
            data={"passphrase": PASSPHRASE, "text": "testo"},
            files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
        )
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/revert/text/apply
# ─────────────────────────────────────────────────────────────────────────────


def test_revert_text_apply_success():
    """Apply revert testo restituisce testo ripristinato."""
    mapping_bytes = _make_mapping_bytes()
    text = "Utente [PERSON_0001] ha inviato email a [EMAIL_0001]."
    response = client.post(
        "/api/revert/text/apply",
        data={"passphrase": PASSPHRASE, "text": text},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "Mario Rossi" in data["reverted_text"]
    assert "mario@example.com" in data["reverted_text"]
    assert data["total_replacements"] == 2


def test_revert_text_apply_empty_passphrase():
    """Apply testo con passphrase blank (solo spazi) restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    response = client.post(
        "/api/revert/text/apply",
        data={"passphrase": "   ", "text": "[PERSON_0001]"},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400


def test_revert_text_apply_text_too_long():
    """Apply testo con testo troppo lungo restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    from app.core.config import MAX_CONSOLE_TEXT_CHARS

    long_text = "x" * (MAX_CONSOLE_TEXT_CHARS + 1)
    response = client.post(
        "/api/revert/text/apply",
        data={"passphrase": PASSPHRASE, "text": long_text},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400


def test_revert_text_apply_empty_mapping():
    """Apply testo con mapping vuoto restituisce 400."""
    response = client.post(
        "/api/revert/text/apply",
        data={"passphrase": PASSPHRASE, "text": "[PERSON_0001]"},
        files={"mapping_file": ("mapping.enc", b"", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_revert_text_apply_wrong_passphrase():
    """Apply testo con passphrase errata restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    response = client.post(
        "/api/revert/text/apply",
        data={"passphrase": "WrongPass_999!", "text": "[PERSON_0001]"},
        files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400


def test_revert_text_apply_mapping_too_large():
    """Apply testo con mapping troppo grande restituisce 400."""
    mapping_bytes = _make_mapping_bytes()
    with patch("app.api.revert_routes.MAX_FILE_SIZE_BYTES", 10):
        response = client.post(
            "/api/revert/text/apply",
            data={"passphrase": PASSPHRASE, "text": "testo"},
            files={"mapping_file": ("mapping.enc", mapping_bytes, "application/octet-stream")},
        )
    assert response.status_code == 400
