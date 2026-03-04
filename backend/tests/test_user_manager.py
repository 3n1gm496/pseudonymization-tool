"""
Test suite per app.core.user_manager.

Copre:
- Inizializzazione DB e bootstrap admin
- CRUD utenti (create, get, list, update_role, update_password, delete)
- verify_credentials (successo, password errata, utente inesistente, utente inattivo)
- Protezione ultimo admin
- Validazioni input
"""

import os
import tempfile
from pathlib import Path

import pytest

import app.core.user_manager as um


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Ogni test usa un DB SQLite isolato in una directory temporanea.
    Resetta anche il path cached del DB.
    """
    db_dir = tmp_path / "state"
    db_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PSEUDONYMIZER_STATE_DIR", str(db_dir))
    # Reset del path cached per forzare la ricreazione
    monkeypatch.setattr(um, "_db_path", None)
    um.initialize()
    yield
    # Cleanup: reset path cached dopo il test
    um._db_path = None


# ─── Inizializzazione e bootstrap ────────────────────────────────────────────


class TestInitialize:
    def test_creates_default_admin_when_no_users(self, monkeypatch):
        """Bootstrap crea admin con credenziali da env."""
        monkeypatch.setattr(um, "DEFAULT_ADMIN_USERNAME", "testadmin")
        monkeypatch.setattr(um, "DEFAULT_ADMIN_PASSWORD", "")
        # Il DB è già inizializzato dal fixture (con admin), verifichiamo che esista
        users = um.list_users()
        assert len(users) >= 1
        admin_users = [u for u in users if u["role"] == "admin"]
        assert len(admin_users) >= 1

    def test_no_bootstrap_if_users_exist(self):
        """Bootstrap non crea un secondo admin se esistono già utenti."""
        initial_count = len(um.list_users())
        # Chiama initialize di nuovo
        um.initialize()
        assert len(um.list_users()) == initial_count

    def test_bootstrap_with_auth_password_env(self, monkeypatch, tmp_path):
        """Bootstrap usa AUTH_PASSWORD se configurata."""
        db_dir = tmp_path / "state2"
        db_dir.mkdir()
        monkeypatch.setenv("PSEUDONYMIZER_STATE_DIR", str(db_dir))
        monkeypatch.setattr(um, "_db_path", None)
        monkeypatch.setattr(um, "DEFAULT_ADMIN_USERNAME", "myadmin")
        monkeypatch.setattr(um, "DEFAULT_ADMIN_PASSWORD", "MySecurePass123!")
        um.initialize()
        role = um.verify_credentials("myadmin", "MySecurePass123!")
        assert role == "admin"
        um._db_path = None


# ─── Create user ─────────────────────────────────────────────────────────────


class TestCreateUser:
    def test_create_operator_user(self):
        um.create_user("alice", "password123", "operator")
        user = um.get_user("alice")
        assert user is not None
        assert user["username"] == "alice"
        assert user["role"] == "operator"
        assert user["is_active"] == 1

    def test_create_admin_user(self):
        um.create_user("bob", "password123", "admin")
        user = um.get_user("bob")
        assert user["role"] == "admin"

    def test_create_user_default_role_is_operator(self):
        um.create_user("charlie", "password123")
        user = um.get_user("charlie")
        assert user["role"] == "operator"

    def test_create_user_normalizes_username_lowercase(self):
        um.create_user("DAVE", "password123", "operator")
        user = um.get_user("dave")
        assert user is not None

    def test_create_user_strips_whitespace(self):
        um.create_user("  eve  ", "password123", "operator")
        user = um.get_user("eve")
        assert user is not None

    def test_create_user_duplicate_raises(self):
        um.create_user("frank", "password123", "operator")
        with pytest.raises(ValueError, match="esiste già"):
            um.create_user("frank", "otherpassword", "operator")

    def test_create_user_empty_username_raises(self):
        with pytest.raises(ValueError, match="non può essere vuoto"):
            um.create_user("", "password123", "operator")

    def test_create_user_whitespace_username_raises(self):
        with pytest.raises(ValueError, match="non può essere vuoto"):
            um.create_user("   ", "password123", "operator")

    def test_create_user_short_password_raises(self):
        with pytest.raises(ValueError, match="almeno 8 caratteri"):
            um.create_user("grace", "short", "operator")

    def test_create_user_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Ruolo non valido"):
            um.create_user("henry", "password123", "superuser")

    def test_create_user_empty_password_raises(self):
        with pytest.raises(ValueError, match="almeno 8 caratteri"):
            um.create_user("ivan", "", "operator")


# ─── Get user ─────────────────────────────────────────────────────────────────


class TestGetUser:
    def test_get_existing_user(self):
        um.create_user("julia", "password123", "operator")
        user = um.get_user("julia")
        assert user is not None
        assert "username" in user
        assert "role" in user
        assert "created_at" in user
        assert "updated_at" in user
        assert "is_active" in user
        assert "password_hash" not in user

    def test_get_nonexistent_user_returns_none(self):
        result = um.get_user("nobody")
        assert result is None


# ─── List users ───────────────────────────────────────────────────────────────


class TestListUsers:
    def test_list_returns_all_users(self):
        um.create_user("user1", "password123", "operator")
        um.create_user("user2", "password123", "admin")
        users = um.list_users()
        usernames = [u["username"] for u in users]
        assert "user1" in usernames
        assert "user2" in usernames

    def test_list_sorted_by_username(self):
        um.create_user("zeta", "password123", "operator")
        um.create_user("alpha", "password123", "operator")
        users = um.list_users()
        usernames = [u["username"] for u in users]
        assert usernames == sorted(usernames)

    def test_list_does_not_include_password_hash(self):
        users = um.list_users()
        for user in users:
            assert "password_hash" not in user


# ─── Update role ──────────────────────────────────────────────────────────────


class TestUpdateUserRole:
    def test_update_role_operator_to_admin(self):
        um.create_user("kate", "password123", "operator")
        um.update_user_role("kate", "admin")
        user = um.get_user("kate")
        assert user["role"] == "admin"

    def test_update_role_admin_to_operator(self):
        # Crea un secondo admin prima di declassare il primo
        um.create_user("leo", "password123", "admin")
        # Recupera l'admin di bootstrap e declassalo
        users = um.list_users()
        admin_users = [u for u in users if u["role"] == "admin"]
        assert len(admin_users) >= 2
        # Aggiorna ruolo di leo
        um.update_user_role("leo", "operator")
        user = um.get_user("leo")
        assert user["role"] == "operator"

    def test_update_role_invalid_role_raises(self):
        um.create_user("mike", "password123", "operator")
        with pytest.raises(ValueError, match="Ruolo non valido"):
            um.update_user_role("mike", "god")

    def test_update_role_nonexistent_user_raises(self):
        with pytest.raises(ValueError, match="non trovato"):
            um.update_user_role("nobody", "operator")


# ─── Update password ──────────────────────────────────────────────────────────


class TestUpdateUserPassword:
    def test_update_password_success(self):
        um.create_user("nina", "oldpassword123", "operator")
        um.update_user_password("nina", "newpassword456")
        # Vecchia password non funziona più
        assert um.verify_credentials("nina", "oldpassword123") is None
        # Nuova password funziona
        assert um.verify_credentials("nina", "newpassword456") == "operator"

    def test_update_password_too_short_raises(self):
        um.create_user("oscar", "password123", "operator")
        with pytest.raises(ValueError, match="almeno 8 caratteri"):
            um.update_user_password("oscar", "short")

    def test_update_password_empty_raises(self):
        um.create_user("penny", "password123", "operator")
        with pytest.raises(ValueError, match="almeno 8 caratteri"):
            um.update_user_password("penny", "")

    def test_update_password_nonexistent_user_raises(self):
        with pytest.raises(ValueError, match="non trovato"):
            um.update_user_password("nobody", "newpassword123")


# ─── Delete user ──────────────────────────────────────────────────────────────


class TestDeleteUser:
    def test_delete_operator_user(self):
        um.create_user("quinn", "password123", "operator")
        um.delete_user("quinn")
        assert um.get_user("quinn") is None

    def test_delete_nonexistent_user_raises(self):
        with pytest.raises(ValueError, match="non trovato"):
            um.delete_user("nobody")

    def test_delete_last_admin_raises(self):
        """Non è possibile eliminare l'ultimo admin."""
        users = um.list_users()
        admins = [u for u in users if u["role"] == "admin"]
        assert len(admins) == 1
        last_admin = admins[0]["username"]
        with pytest.raises(ValueError, match="ultimo utente admin"):
            um.delete_user(last_admin)

    def test_delete_admin_when_another_admin_exists(self):
        """Si può eliminare un admin se ne esiste un altro."""
        um.create_user("rachel", "password123", "admin")
        um.create_user("sam", "password123", "admin")
        um.delete_user("rachel")
        assert um.get_user("rachel") is None


# ─── Verify credentials ───────────────────────────────────────────────────────


class TestVerifyCredentials:
    def test_valid_credentials_returns_role(self):
        um.create_user("tina", "password123", "operator")
        result = um.verify_credentials("tina", "password123")
        assert result == "operator"

    def test_valid_admin_credentials(self):
        um.create_user("uma", "password123", "admin")
        result = um.verify_credentials("uma", "password123")
        assert result == "admin"

    def test_wrong_password_returns_none(self):
        um.create_user("victor", "password123", "operator")
        result = um.verify_credentials("victor", "wrongpassword")
        assert result is None

    def test_nonexistent_user_returns_none(self):
        result = um.verify_credentials("nobody", "password123")
        assert result is None

    def test_empty_username_returns_none(self):
        result = um.verify_credentials("", "password123")
        assert result is None

    def test_empty_password_returns_none(self):
        result = um.verify_credentials("admin", "")
        assert result is None

    def test_case_insensitive_username(self):
        um.create_user("wendy", "password123", "operator")
        result = um.verify_credentials("WENDY", "password123")
        assert result == "operator"

    def test_inactive_user_returns_none(self):
        """Utente con is_active=0 non può autenticarsi."""
        um.create_user("xavier", "password123", "operator")
        # Disattiva l'utente direttamente nel DB
        with um._get_conn() as conn:
            conn.execute("UPDATE users SET is_active = 0 WHERE username = 'xavier'")
        result = um.verify_credentials("xavier", "password123")
        assert result is None


# ─── Get user role ────────────────────────────────────────────────────────────


class TestGetUserRole:
    def test_get_role_existing_user(self):
        um.create_user("yara", "password123", "operator")
        role = um.get_user_role("yara")
        assert role == "operator"

    def test_get_role_admin_user(self):
        um.create_user("zack", "password123", "admin")
        role = um.get_user_role("zack")
        assert role == "admin"

    def test_get_role_nonexistent_user_returns_none(self):
        role = um.get_user_role("nobody")
        assert role is None

    def test_get_role_inactive_user_returns_none(self):
        um.create_user("abby", "password123", "operator")
        with um._get_conn() as conn:
            conn.execute("UPDATE users SET is_active = 0 WHERE username = 'abby'")
        role = um.get_user_role("abby")
        assert role is None


# ─── Count admins ─────────────────────────────────────────────────────────────


class TestCountAdmins:
    def test_count_admins_initial(self):
        count = um.count_admins()
        assert count >= 1

    def test_count_admins_after_adding(self):
        initial = um.count_admins()
        um.create_user("beth", "password123", "admin")
        assert um.count_admins() == initial + 1

    def test_count_admins_after_role_change(self):
        um.create_user("carl", "password123", "admin")
        initial = um.count_admins()
        um.update_user_role("carl", "operator")
        assert um.count_admins() == initial - 1


# ─── Helper functions ─────────────────────────────────────────────────────────


class TestHelperFunctions:
    def test_hash_and_check_password(self):
        hashed = um._hash_password("mypassword")
        assert um._check_password("mypassword", hashed) is True
        assert um._check_password("wrongpassword", hashed) is False

    def test_check_password_invalid_hash(self):
        """_check_password ritorna False su hash non valido."""
        result = um._check_password("password", "not_a_valid_hash")
        assert result is False

    def test_dummy_verify_does_not_raise(self):
        """_dummy_verify non deve sollevare eccezioni."""
        um._dummy_verify()

    def test_get_db_path_uses_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PSEUDONYMIZER_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(um, "_db_path", None)
        path = um._get_db_path()
        assert path == tmp_path / "users.db"
        um._db_path = None

    def test_get_db_path_uses_tempdir_fallback(self, monkeypatch):
        monkeypatch.delenv("PSEUDONYMIZER_STATE_DIR", raising=False)
        monkeypatch.setattr(um, "_db_path", None)
        path = um._get_db_path()
        assert "pseudonymizer_batches" in str(path)
        um._db_path = None
