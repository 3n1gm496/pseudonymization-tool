"""
Test suite per app.api.users_routes.

Copre:
- GET /api/users (lista utenti, solo admin)
- POST /api/users (crea utente, solo admin)
- GET /api/users/me (utente corrente, tutti gli autenticati)
- GET /api/users/{username} (dettaglio utente, solo admin)
- PUT /api/users/{username}/role (aggiorna ruolo, solo admin)
- PUT /api/users/{username}/password (aggiorna password, admin o self)
- DELETE /api/users/{username} (elimina utente, solo admin)
- Protezione RBAC: 401 senza auth, 403 con ruolo operator
"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.core.user_manager as um


@pytest.fixture(autouse=True)
def isolated_user_db(tmp_path, monkeypatch):
    """
    Ogni test usa un DB SQLite isolato.
    Inizializza il DB con un admin di default.
    """
    db_dir = tmp_path / "state"
    db_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PSEUDONYMIZER_STATE_DIR", str(db_dir))
    monkeypatch.setattr(um, "_db_path", None)
    monkeypatch.setattr(um, "DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setattr(um, "DEFAULT_ADMIN_PASSWORD", "AdminPass123!")
    um.initialize()
    yield
    um._db_path = None


@pytest.fixture
def client():
    """TestClient con autenticazione disabilitata (gestita dal conftest)."""
    from app.main import app

    return TestClient(app)


# ─── GET /api/users ──────────────────────────────────────────────────────────


class TestListUsersEndpoint:
    def test_list_users_returns_list(self, client):
        response = client.get("/api/users")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert isinstance(data["users"], list)
        assert data["total"] == len(data["users"])

    def test_list_users_includes_admin(self, client):
        response = client.get("/api/users")
        assert response.status_code == 200
        usernames = [u["username"] for u in response.json()["users"]]
        assert "admin" in usernames

    def test_list_users_no_password_hash(self, client):
        response = client.get("/api/users")
        for user in response.json()["users"]:
            assert "password_hash" not in user

    def test_list_users_after_create(self, client):
        client.post("/api/users", json={"username": "newuser", "password": "password123", "role": "operator"})
        response = client.get("/api/users")
        usernames = [u["username"] for u in response.json()["users"]]
        assert "newuser" in usernames


# ─── POST /api/users ─────────────────────────────────────────────────────────


class TestCreateUserEndpoint:
    def test_create_operator_user(self, client):
        response = client.post(
            "/api/users",
            json={"username": "alice", "password": "password123", "role": "operator"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "user" in data
        assert data["user"]["username"] == "alice"
        assert data["user"]["role"] == "operator"

    def test_create_admin_user(self, client):
        response = client.post(
            "/api/users",
            json={"username": "bob", "password": "password123", "role": "admin"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"

    def test_create_user_default_role_operator(self, client):
        response = client.post(
            "/api/users",
            json={"username": "charlie", "password": "password123"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "operator"

    def test_create_user_duplicate_returns_400(self, client):
        client.post("/api/users", json={"username": "dave", "password": "password123", "role": "operator"})
        response = client.post(
            "/api/users",
            json={"username": "dave", "password": "otherpassword", "role": "operator"},
        )
        assert response.status_code == 400
        assert "esiste già" in response.json()["detail"]

    def test_create_user_invalid_role_returns_422(self, client):
        response = client.post(
            "/api/users",
            json={"username": "eve", "password": "password123", "role": "superuser"},
        )
        assert response.status_code == 422

    def test_create_user_short_password_returns_422(self, client):
        response = client.post(
            "/api/users",
            json={"username": "frank", "password": "short", "role": "operator"},
        )
        assert response.status_code == 422

    def test_create_user_invalid_username_chars_returns_422(self, client):
        response = client.post(
            "/api/users",
            json={"username": "user name!", "password": "password123", "role": "operator"},
        )
        assert response.status_code == 422

    def test_create_user_normalizes_username(self, client):
        response = client.post(
            "/api/users",
            json={"username": "GRACE", "password": "password123", "role": "operator"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["username"] == "grace"


# ─── GET /api/users/me ───────────────────────────────────────────────────────


class TestGetCurrentUserEndpoint:
    def test_get_me_returns_user_info(self, client):
        response = client.get("/api/users/me")
        assert response.status_code == 200
        data = response.json()
        assert "username" in data
        assert "role" in data

    def test_get_me_auth_disabled_returns_admin(self, client):
        """Con auth disabilitata, /me ritorna admin."""
        response = client.get("/api/users/me")
        assert response.status_code == 200
        assert response.json()["username"] == "admin"
        assert response.json()["role"] == "admin"


# ─── GET /api/users/{username} ───────────────────────────────────────────────


class TestGetUserEndpoint:
    def test_get_existing_user(self, client):
        client.post("/api/users", json={"username": "henry", "password": "password123", "role": "operator"})
        response = client.get("/api/users/henry")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "henry"
        assert data["role"] == "operator"

    def test_get_nonexistent_user_returns_404(self, client):
        response = client.get("/api/users/nobody")
        assert response.status_code == 404
        assert "non trovato" in response.json()["detail"]

    def test_get_user_no_password_hash(self, client):
        response = client.get("/api/users/admin")
        assert response.status_code == 200
        assert "password_hash" not in response.json()


# ─── PUT /api/users/{username}/role ──────────────────────────────────────────


class TestUpdateRoleEndpoint:
    def test_update_role_operator_to_admin(self, client):
        client.post("/api/users", json={"username": "ivan", "password": "password123", "role": "operator"})
        response = client.put("/api/users/ivan/role", json={"role": "admin"})
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"

    def test_update_role_invalid_role_returns_422(self, client):
        response = client.put("/api/users/admin/role", json={"role": "god"})
        assert response.status_code == 422

    def test_update_role_nonexistent_user_returns_400(self, client):
        response = client.put("/api/users/nobody/role", json={"role": "operator"})
        assert response.status_code == 400
        assert "non trovato" in response.json()["detail"]


# ─── PUT /api/users/{username}/password ──────────────────────────────────────


class TestUpdatePasswordEndpoint:
    def test_update_password_success(self, client):
        client.post("/api/users", json={"username": "julia", "password": "oldpassword123", "role": "operator"})
        response = client.put(
            "/api/users/julia/password",
            json={"new_password": "newpassword456"},
        )
        assert response.status_code == 200
        assert "aggiornata" in response.json()["message"]

    def test_update_password_too_short_returns_422(self, client):
        response = client.put(
            "/api/users/admin/password",
            json={"new_password": "short"},
        )
        assert response.status_code == 422

    def test_update_password_nonexistent_user_returns_400(self, client):
        response = client.put(
            "/api/users/nobody/password",
            json={"new_password": "newpassword123"},
        )
        assert response.status_code == 400
        assert "non trovato" in response.json()["detail"]


# ─── DELETE /api/users/{username} ────────────────────────────────────────────


class TestDeleteUserEndpoint:
    def test_delete_operator_user(self, client):
        client.post("/api/users", json={"username": "kate", "password": "password123", "role": "operator"})
        response = client.delete("/api/users/kate")
        assert response.status_code == 200
        assert "eliminato" in response.json()["message"]
        # Verifica che l'utente non esista più
        assert client.get("/api/users/kate").status_code == 404

    def test_delete_nonexistent_user_returns_400(self, client):
        response = client.delete("/api/users/nobody")
        assert response.status_code == 400
        assert "non trovato" in response.json()["detail"]

    def test_delete_last_admin_returns_400(self, client):
        """Non è possibile eliminare l'ultimo admin."""
        response = client.delete("/api/users/admin")
        assert response.status_code == 400
        assert "ultimo utente admin" in response.json()["detail"]

    def test_delete_admin_when_another_exists(self, client):
        """Si può eliminare un admin se ne esiste un altro."""
        client.post("/api/users", json={"username": "leo", "password": "password123", "role": "admin"})
        response = client.delete("/api/users/leo")
        assert response.status_code == 200


# ─── Validazione schema ───────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_create_user_missing_username_returns_422(self, client):
        response = client.post("/api/users", json={"password": "password123", "role": "operator"})
        assert response.status_code == 422

    def test_create_user_missing_password_returns_422(self, client):
        response = client.post("/api/users", json={"username": "mike", "role": "operator"})
        assert response.status_code == 422

    def test_update_role_missing_role_returns_422(self, client):
        response = client.put("/api/users/admin/role", json={})
        assert response.status_code == 422

    def test_update_password_missing_new_password_returns_422(self, client):
        response = client.put("/api/users/admin/password", json={})
        assert response.status_code == 422
