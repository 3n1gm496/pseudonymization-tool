import io
import zipfile

from app.api import auth_routes, console_routes
from app.core.batch_manager import create_batch, get_batch_dir
from app.main import app
from app.models.schemas import Batch, BatchConfig, BatchStatus, FileRecord, PresetName, SafetyLabel
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_and_ready_contract():
    health = client.get("/api/health")
    assert health.status_code == 200
    health_data = health.json()
    assert "status" in health_data
    assert "service" in health_data
    assert "version" in health_data

    ready = client.get("/api/ready")
    assert ready.status_code == 200
    ready_data = ready.json()
    assert "ready" in ready_data
    assert "checks" in ready_data


def test_policy_preview_contract():
    presets = client.get("/api/settings/policies")
    assert presets.status_code == 200
    assert "presets" in presets.json()

    preview = client.get("/api/settings/policies/SOC%20Logs")
    assert preview.status_code == 200
    body = preview.json()
    assert body["preset"] == "SOC Logs"
    assert "enabled_entity_types" in body
    assert "confidence_threshold" in body


def test_console_scan_contract(monkeypatch):
    def fake_run_text_scan(batch_id: str, text: str, label: str):
        return "file-contract-1", [], SafetyLabel.SAFE_TO_UPLOAD

    monkeypatch.setattr(console_routes, "run_text_scan", fake_run_text_scan)

    response = client.post(
        "/api/console/scan",
        json={
            "text": "email: test@example.com",
            "mode": "light",
            "preset": "SOC Logs",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    assert "file_id" in data
    assert "passphrase" in data
    assert "findings" in data
    assert "safety_label" in data


def test_console_apply_contract(monkeypatch):
    def fake_run_text_scan(batch_id: str, text: str, label: str):
        return "file-contract-2", [], SafetyLabel.SAFE_TO_UPLOAD

    def fake_run_text_apply(batch_id: str, file_id: str, original_text: str):
        return "masked text", SafetyLabel.SAFE_TO_UPLOAD, [], 1

    monkeypatch.setattr(console_routes, "run_text_scan", fake_run_text_scan)
    monkeypatch.setattr(console_routes, "run_text_apply", fake_run_text_apply)

    scan = client.post(
        "/api/console/scan",
        json={
            "text": "user@example.com",
            "mode": "light",
            "preset": "SOC Logs",
        },
    )
    assert scan.status_code == 200
    scan_data = scan.json()

    apply_resp = client.post(
        "/api/console/apply",
        json={
            "batch_id": scan_data["batch_id"],
            "file_id": scan_data["file_id"],
            "text": "user@example.com",
        },
    )

    assert apply_resp.status_code == 200
    apply_data = apply_resp.json()
    assert apply_data["batch_id"] == scan_data["batch_id"]
    assert "pseudonymized_text" in apply_data
    assert "safety_label" in apply_data
    assert "applied_count" in apply_data


def test_batch_create_contract():
    """
    Test batch creation endpoint contract.
    After Phase 4 async refactor: returns 202 (Accepted) with task_id instead of 200.
    Celery runs in EAGER mode for testing, so tasks execute synchronously.
    """
    file_content = io.BytesIO(b"Utente: alice@example.com")
    response = client.post(
        "/api/batches",
        data={
            "mode": "light",
            "preset": "SOC Logs",
            "passphrase": "Str0ng!Passphrase#2026X",
        },
        files={"files": ("contract.txt", file_content, "text/plain")},
    )

    # After Phase 4: endpoint returns 202 (Accepted) with async task enqueued
    assert response.status_code == 202
    body = response.json()
    assert "batch_id" in body
    assert "status" in body
    assert "files" in body
    assert "findings_count" in body
    assert "task_id" in body  # Async task tracking
    assert "message" in body  # Queue acknowledgment message


def test_download_blocked_when_done_with_errors():
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.DONE_WITH_ERRORS
    batch.safety_label = SafetyLabel.SAFE_TO_UPLOAD
    batch.files = [
        FileRecord(
            original_name="contract.txt",
            stored_path="/tmp/contract.txt",
            is_text_input=False,
        )
    ]
    create_batch(batch)

    batch_dir = get_batch_dir(batch.batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    zip_path = batch_dir / "artifact.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        payload = batch_dir / "payload.txt"
        payload.write_text("dummy", encoding="utf-8")
        zf.write(payload, arcname="payload.txt")

    response = client.get(f"/api/batches/{batch.batch_id}/download")
    assert response.status_code == 409
    assert "done_with_errors" in response.json()["detail"]


def test_download_blocked_when_not_safe():
    batch = Batch(config=BatchConfig(preset=PresetName.SOC_LOGS))
    batch.status = BatchStatus.DONE
    batch.safety_label = SafetyLabel.NOT_SAFE
    batch.files = [
        FileRecord(
            original_name="contract.txt",
            stored_path="/tmp/contract.txt",
            is_text_input=False,
        )
    ]
    create_batch(batch)

    batch_dir = get_batch_dir(batch.batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    zip_path = batch_dir / "artifact.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        payload = batch_dir / "payload.txt"
        payload.write_text("dummy", encoding="utf-8")
        zf.write(payload, arcname="payload.txt")

    response = client.get(f"/api/batches/{batch.batch_id}/download")
    assert response.status_code == 409
    assert "safety_label" in response.json()["detail"]


def test_auth_login_sets_secure_cookie_by_default(monkeypatch):
    monkeypatch.setattr(auth_routes, "SESSION_COOKIE_SECURE", True)

    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123!"})
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "Secure" in set_cookie


def test_auth_login_allows_dev_override_without_secure_cookie(monkeypatch):
    monkeypatch.setattr(auth_routes, "SESSION_COOKIE_SECURE", False)

    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123!"})
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "Secure" not in set_cookie
