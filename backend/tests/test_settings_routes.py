"""
Test suite for settings_routes.py

Coverage targets:
  - GET /api/settings/state
  - POST /api/settings/state
  - GET /api/settings/dictionaries
  - POST /api/settings/dictionaries/reload
  - GET /api/settings/ldap
  - POST /api/settings/ldap
  - POST /api/settings/ldap/test
  - POST /api/settings/ldap/refresh
  - GET /api/settings/entity-types
  - GET /api/settings/policies
  - GET /api/settings/policies/{preset_name}
"""

import json
from unittest.mock import MagicMock, patch

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


# ─── GET /api/settings/entity-types ──────────────────────────────────────────


def test_get_entity_types_returns_list():
    """GET /api/settings/entity-types returns a non-empty list of entity types."""
    response = client.get("/api/settings/entity-types")
    assert response.status_code == 200
    data = response.json()
    assert "entity_types" in data
    assert isinstance(data["entity_types"], list)
    assert len(data["entity_types"]) > 0
    # Each item should have 'value' and 'label'
    for item in data["entity_types"]:
        assert "value" in item
        assert "label" in item


# ─── GET /api/settings/policies ───────────────────────────────────────────────


def test_get_policies_returns_presets():
    """GET /api/settings/policies returns available preset names."""
    response = client.get("/api/settings/policies")
    assert response.status_code == 200
    data = response.json()
    assert "presets" in data
    assert isinstance(data["presets"], list)
    assert len(data["presets"]) > 0
    # SOC Logs preset should always be present
    assert "SOC Logs" in data["presets"]


# ─── GET /api/settings/policies/{preset_name} ─────────────────────────────────


def test_get_policy_preview_valid_preset():
    """GET /api/settings/policies/SOC%20Logs returns policy details."""
    response = client.get("/api/settings/policies/SOC%20Logs")
    assert response.status_code == 200
    data = response.json()
    assert data["preset"] == "SOC Logs"
    assert "confidence_threshold" in data
    assert "enabled_entity_types" in data
    assert "entity_count" in data
    assert isinstance(data["entity_count"], int)
    assert data["entity_count"] > 0


def test_get_policy_preview_all_presets():
    """GET /api/settings/policies/{preset} works for all available presets."""
    presets_resp = client.get("/api/settings/policies")
    presets = presets_resp.json()["presets"]

    for preset in presets:
        encoded = preset.replace(" ", "%20")
        response = client.get(f"/api/settings/policies/{encoded}")
        assert response.status_code == 200, f"Failed for preset: {preset}"
        data = response.json()
        assert data["preset"] == preset


def test_get_policy_preview_invalid_preset():
    """GET /api/settings/policies/invalid returns 400."""
    response = client.get("/api/settings/policies/NonExistentPreset")
    assert response.status_code == 400
    assert "Preset non valido" in response.json()["detail"]


# ─── GET /api/settings/state ──────────────────────────────────────────────────


def test_get_server_state_returns_default_when_no_file(tmp_path):
    """GET /api/settings/state returns default state when file doesn't exist."""
    import app.api.settings_routes as sr

    with patch.object(sr, "_STATE_FILE", tmp_path / "nonexistent.json"):
        response = client.get("/api/settings/state")
    assert response.status_code == 200
    data = response.json()
    assert "mode" in data
    assert data["mode"] == "light"


def test_get_server_state_returns_persisted_state(tmp_path):
    """GET /api/settings/state returns persisted state when file exists."""
    import app.api.settings_routes as sr

    state_file = tmp_path / "state.json"
    state_data = {"mode": "dark", "ldap": None, "sessions_metadata": []}
    state_file.write_text(json.dumps(state_data), encoding="utf-8")

    with patch.object(sr, "_STATE_FILE", state_file):
        response = client.get("/api/settings/state")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "dark"


def test_get_server_state_returns_default_on_corrupt_file(tmp_path):
    """GET /api/settings/state returns default state when file is corrupt."""
    import app.api.settings_routes as sr

    state_file = tmp_path / "state.json"
    state_file.write_text("not valid json", encoding="utf-8")

    with patch.object(sr, "_STATE_FILE", state_file):
        response = client.get("/api/settings/state")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "light"


# ─── POST /api/settings/state ─────────────────────────────────────────────────


def test_save_server_state_ok(tmp_path):
    """POST /api/settings/state saves state and returns ok."""
    import app.api.settings_routes as sr

    state_file = tmp_path / "state.json"

    with patch.object(sr, "_STATE_FILE", state_file):
        response = client.post(
            "/api/settings/state",
            json={"mode": "dark", "ldap": None},
        )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    # Verify file was written
    assert state_file.exists()
    saved = json.loads(state_file.read_text())
    assert saved["mode"] == "dark"


def test_save_server_state_scrubs_password(tmp_path):
    """POST /api/settings/state removes sensitive fields before saving."""
    import app.api.settings_routes as sr

    state_file = tmp_path / "state.json"
    payload = {
        "mode": "light",
        "ldap": {
            "host": "ldap.example.com",
            "bind_password": "supersecret",
        },
    }

    with patch.object(sr, "_STATE_FILE", state_file):
        response = client.post("/api/settings/state", json=payload)
    assert response.status_code == 200

    saved = json.loads(state_file.read_text())
    # bind_password must be scrubbed
    if saved.get("ldap"):
        assert "bind_password" not in saved["ldap"]


def test_save_server_state_error_on_write_failure(tmp_path):
    """POST /api/settings/state returns 500 when write fails."""
    import app.api.settings_routes as sr

    # Point to a read-only path
    state_file = tmp_path / "readonly_dir" / "state.json"

    with patch.object(sr, "_STATE_FILE", state_file):
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("read-only")):
            response = client.post("/api/settings/state", json={"mode": "light"})
    assert response.status_code == 500


# ─── GET /api/settings/dictionaries ──────────────────────────────────────────


def test_get_dictionaries_status():
    """GET /api/settings/dictionaries returns total_terms and files count."""
    mock_detector = MagicMock()
    mock_detector.loaded_terms_count = 42

    with patch("app.detectors.dictionary_detector.get_dictionary_detector", return_value=mock_detector):
        response = client.get("/api/settings/dictionaries")

    assert response.status_code == 200
    data = response.json()
    assert "total_terms" in data
    assert data["total_terms"] == 42
    assert "files" in data


# ─── POST /api/settings/dictionaries/reload ───────────────────────────────────


def test_reload_dictionaries():
    """POST /api/settings/dictionaries/reload triggers reload and returns count."""
    mock_detector = MagicMock()
    mock_detector.loaded_terms_count = 100

    with patch("app.detectors.dictionary_detector.get_dictionary_detector", return_value=mock_detector):
        response = client.post("/api/settings/dictionaries/reload")

    assert response.status_code == 200
    data = response.json()
    assert data["total_terms"] == 100
    assert "message" in data
    mock_detector.reload.assert_called_once()


# ─── GET /api/settings/ldap ───────────────────────────────────────────────────


def test_get_ldap_config_not_configured():
    """GET /api/settings/ldap returns enabled=False when not configured."""
    mock_cache = MagicMock()
    mock_cache.get_diagnostics.return_value = {}

    with patch("app.detectors.ldap_detector.get_ldap_config", return_value=None):
        with patch("app.detectors.ldap_detector.get_ldap_cache", return_value=mock_cache):
            response = client.get("/api/settings/ldap")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["configured"] is False


def test_get_ldap_config_configured():
    """GET /api/settings/ldap returns config with password redacted when configured."""
    mock_cfg = MagicMock()
    mock_cfg.model_dump.return_value = {
        "host": "ldap.example.com",
        "port": 389,
        "enabled": True,
        "bind_password": "should_be_removed",
    }
    mock_cache = MagicMock()
    mock_cache.get_diagnostics.return_value = {"status": "ok"}

    with patch("app.detectors.ldap_detector.get_ldap_config", return_value=mock_cfg):
        with patch("app.detectors.ldap_detector.get_ldap_cache", return_value=mock_cache):
            response = client.get("/api/settings/ldap")

    assert response.status_code == 200
    data = response.json()
    assert "bind_password" not in data
    assert data["configured"] is True
    assert data["host"] == "ldap.example.com"


# ─── POST /api/settings/ldap ──────────────────────────────────────────────────


def test_set_ldap_config():
    """POST /api/settings/ldap configures LDAP and returns ok."""
    with patch("app.detectors.ldap_detector.configure_ldap") as mock_configure:
        response = client.post(
            "/api/settings/ldap",
            json={
                "host": "ldap.example.com",
                "port": 389,
                "base_dn": "dc=example,dc=com",
                "bind_dn": "cn=admin,dc=example,dc=com",
                "bind_password": "secret",
                "enabled": True,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    mock_configure.assert_called_once()


# ─── POST /api/settings/ldap/test ─────────────────────────────────────────────


def test_ldap_test_connection_success():
    """POST /api/settings/ldap/test returns ok=True on success."""
    mock_cache = MagicMock()
    mock_cache.test_connection.return_value = (True, "Connected", 50, {"status": "ok"})

    with patch("app.detectors.ldap_detector.get_ldap_cache", return_value=mock_cache):
        response = client.post("/api/settings/ldap/test")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["user_count"] == 50
    assert data["error"] is None


def test_ldap_test_connection_failure():
    """POST /api/settings/ldap/test returns ok=False on failure."""
    mock_cache = MagicMock()
    mock_cache.test_connection.return_value = (False, "Connection refused", 0, {"status": "error"})

    with patch("app.detectors.ldap_detector.get_ldap_cache", return_value=mock_cache):
        response = client.post("/api/settings/ldap/test")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "Connection refused"
    assert data["user_count"] == 0


# ─── POST /api/settings/ldap/refresh ──────────────────────────────────────────


def test_ldap_refresh_success():
    """POST /api/settings/ldap/refresh returns ok=True on success."""
    mock_cache = MagicMock()
    mock_cache.refresh_now.return_value = (True, "Refreshed 50 users", {"status": "ok"})

    with patch("app.detectors.ldap_detector.get_ldap_cache", return_value=mock_cache):
        response = client.post("/api/settings/ldap/refresh")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "message" in data


def test_ldap_refresh_failure():
    """POST /api/settings/ldap/refresh returns ok=False on failure."""
    mock_cache = MagicMock()
    mock_cache.refresh_now.return_value = (False, "LDAP unreachable", {"status": "error"})

    with patch("app.detectors.ldap_detector.get_ldap_cache", return_value=mock_cache):
        response = client.post("/api/settings/ldap/refresh")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
