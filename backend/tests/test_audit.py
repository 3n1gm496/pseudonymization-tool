"""
Tests for the audit log module (audit.py) and audit API endpoints (audit_routes.py).

Covers:
- scrub_sensitive: dict, list, str, nested, sensitive keys
- _ensure_schema: idempotent, creates table and indexes
- audit_event: persists to SQLite, scrubs details, handles request/None
- get_audit_events: pagination, filters (action, user, since, until)
- get_audit_stats: totals, by_action, by_user, recent_failures
- API endpoints: GET /api/audit/events, GET /api/audit/stats
"""

import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from app.core.audit import (
    _ensure_schema,
    _get_connection,
    _get_db_path,
    audit_event,
    get_audit_events,
    get_audit_stats,
    scrub_sensitive,
)
from app.main import app
from fastapi.testclient import TestClient

_client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Each test gets its own SQLite database in a temp directory."""
    import app.core.audit as audit_module

    db_path = str(tmp_path / "audit.db")
    # Reset the initialized flag so _ensure_schema runs fresh for each test
    audit_module._DB_INITIALIZED = False
    with patch.dict(os.environ, {"PSEUDONYMIZER_STATE_DIR": str(tmp_path)}):
        yield db_path
    # Reset again after test
    audit_module._DB_INITIALIZED = False


def _make_request(user="testuser", ip="10.0.0.1"):
    """Create a mock FastAPI Request with state.auth_user and client.host."""
    req = MagicMock()
    req.state.auth_user = user
    req.client.host = ip
    return req


# ---------------------------------------------------------------------------
# scrub_sensitive
# ---------------------------------------------------------------------------


class TestScrubSensitive:
    def test_removes_password_key(self):
        result = scrub_sensitive({"password": "secret", "username": "admin"})
        assert "password" not in result
        assert result["username"] == "admin"

    def test_removes_passphrase_key(self):
        result = scrub_sensitive({"passphrase": "abc123", "name": "test"})
        assert "passphrase" not in result

    def test_removes_token_key(self):
        result = scrub_sensitive({"token": "abc", "data": 1})
        assert "token" not in result

    def test_removes_api_key(self):
        result = scrub_sensitive({"api_key": "xyz", "ok": True})
        assert "api_key" not in result

    def test_removes_bind_password(self):
        result = scrub_sensitive({"bind_password": "ldap_pass"})
        assert "bind_password" not in result

    def test_keeps_safe_keys(self):
        result = scrub_sensitive({"username": "admin", "count": 5})
        assert result == {"username": "admin", "count": 5}

    def test_nested_dict(self):
        result = scrub_sensitive({"user": {"password": "x", "name": "bob"}})
        assert "password" not in result["user"]
        assert result["user"]["name"] == "bob"

    def test_list_of_dicts(self):
        result = scrub_sensitive([{"password": "x"}, {"name": "alice"}])
        assert "password" not in result[0]
        assert result[1]["name"] == "alice"

    def test_scrubs_home_path(self):
        result = scrub_sensitive("/home/alice/file.txt")
        assert "/home/***" in result
        assert "alice" not in result

    def test_scrubs_tmp_path(self):
        result = scrub_sensitive("/tmp/somedir/file.csv")
        assert "/tmp/***" in result

    def test_scrubs_uuid(self):
        result = scrub_sensitive("batch-abc12345-6789-4bcd-8e90-123456789abc")
        assert "abc12345-****" in result

    def test_non_string_passthrough(self):
        assert scrub_sensitive(42) == 42
        assert scrub_sensitive(None) is None
        assert scrub_sensitive(True) is True


# ---------------------------------------------------------------------------
# _ensure_schema
# ---------------------------------------------------------------------------


class TestEnsureSchema:
    def test_creates_table(self, isolated_db):
        _ensure_schema()
        conn = _get_connection()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        assert "audit_events" in table_names
        conn.close()

    def test_idempotent(self, isolated_db):
        _ensure_schema()
        _ensure_schema()  # Should not raise
        conn = _get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='audit_events'"
        ).fetchone()[0]
        assert count == 1
        conn.close()

    def test_creates_indexes(self, isolated_db):
        _ensure_schema()
        conn = _get_connection()
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        index_names = [i[0] for i in indexes]
        assert "idx_audit_timestamp" in index_names
        assert "idx_audit_action" in index_names
        assert "idx_audit_user" in index_names
        conn.close()


# ---------------------------------------------------------------------------
# audit_event
# ---------------------------------------------------------------------------


class TestAuditEvent:
    def test_persists_event_with_request(self, isolated_db):
        req = _make_request(user="admin", ip="192.168.1.1")
        audit_event(req, "test_action", key="value")
        result = get_audit_events(limit=10)
        assert result["total"] == 1
        event = result["events"][0]
        assert event["action"] == "test_action"
        assert event["user"] == "admin"
        assert event["ip"] == "192.168.1.1"
        assert event["details"]["key"] == "value"

    def test_persists_event_without_request(self, isolated_db):
        audit_event(None, "system_startup", version="5.0.0")
        result = get_audit_events()
        assert result["total"] == 1
        event = result["events"][0]
        assert event["user"] == "anonymous"
        assert event["ip"] == "unknown"
        assert event["details"]["version"] == "5.0.0"

    def test_scrubs_sensitive_details(self, isolated_db):
        req = _make_request()
        audit_event(req, "auth_login", password="secret", username="admin")
        result = get_audit_events()
        event = result["events"][0]
        assert "password" not in event["details"]
        assert event["details"]["username"] == "admin"

    def test_multiple_events_ordered_desc(self, isolated_db):
        req = _make_request()
        audit_event(req, "action_first")
        audit_event(req, "action_second")
        audit_event(req, "action_third")
        result = get_audit_events(limit=10)
        assert result["total"] == 3
        # Most recent first
        assert result["events"][0]["action"] == "action_third"
        assert result["events"][2]["action"] == "action_first"

    def test_request_without_client(self, isolated_db):
        req = MagicMock()
        req.state.auth_user = "user1"
        req.client = None
        audit_event(req, "test_no_client")
        result = get_audit_events()
        assert result["events"][0]["ip"] == "unknown"


# ---------------------------------------------------------------------------
# get_audit_events — filters and pagination
# ---------------------------------------------------------------------------


class TestGetAuditEvents:
    def _populate(self, n=5):
        req = _make_request(user="admin")
        for i in range(n):
            action = "auth_login" if i % 2 == 0 else "batch_create"
            audit_event(req, action, index=i)

    def test_empty_db(self, isolated_db):
        result = get_audit_events()
        assert result["total"] == 0
        assert result["events"] == []

    def test_pagination_limit(self, isolated_db):
        self._populate(10)
        result = get_audit_events(limit=3)
        assert len(result["events"]) == 3
        assert result["total"] == 10

    def test_pagination_offset(self, isolated_db):
        self._populate(5)
        result_page1 = get_audit_events(limit=2, offset=0)
        result_page2 = get_audit_events(limit=2, offset=2)
        ids_page1 = {e["id"] for e in result_page1["events"]}
        ids_page2 = {e["id"] for e in result_page2["events"]}
        assert ids_page1.isdisjoint(ids_page2)

    def test_filter_by_action(self, isolated_db):
        self._populate(6)
        result = get_audit_events(action_filter="auth_")
        for event in result["events"]:
            assert event["action"].startswith("auth_")

    def test_filter_by_user(self, isolated_db):
        req_admin = _make_request(user="admin")
        req_other = _make_request(user="other")
        audit_event(req_admin, "action_a")
        audit_event(req_other, "action_b")
        result = get_audit_events(user_filter="admin")
        assert result["total"] == 1
        assert result["events"][0]["user"] == "admin"

    def test_filter_by_since(self, isolated_db):
        from datetime import datetime, timedelta, timezone

        req = _make_request()
        audit_event(req, "old_action")
        # Use a timestamp slightly in the future to filter out the old event
        future = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        audit_event(req, "new_action")
        result = get_audit_events(since=future)
        # Only the new action (inserted after future timestamp) should appear
        for event in result["events"]:
            assert event["timestamp"] >= future

    def test_limit_capped_at_500(self, isolated_db):
        result = get_audit_events(limit=9999)
        assert result["limit"] == 500

    def test_limit_minimum_1(self, isolated_db):
        result = get_audit_events(limit=0)
        assert result["limit"] == 1


# ---------------------------------------------------------------------------
# get_audit_stats
# ---------------------------------------------------------------------------


class TestGetAuditStats:
    def test_empty_db(self, isolated_db):
        stats = get_audit_stats()
        assert stats["total_events"] == 0
        assert stats["events_by_action"] == []
        assert stats["events_by_user"] == []
        assert stats["recent_failures"] == []

    def test_total_events(self, isolated_db):
        req = _make_request()
        for _ in range(7):
            audit_event(req, "some_action")
        stats = get_audit_stats()
        assert stats["total_events"] == 7

    def test_events_by_action(self, isolated_db):
        req = _make_request()
        for _ in range(3):
            audit_event(req, "auth_login")
        for _ in range(2):
            audit_event(req, "batch_create")
        stats = get_audit_stats()
        by_action = {e["action"]: e["count"] for e in stats["events_by_action"]}
        assert by_action["auth_login"] == 3
        assert by_action["batch_create"] == 2

    def test_events_by_user(self, isolated_db):
        req_a = _make_request(user="alice")
        req_b = _make_request(user="bob")
        audit_event(req_a, "action")
        audit_event(req_a, "action")
        audit_event(req_b, "action")
        stats = get_audit_stats()
        by_user = {e["user"]: e["count"] for e in stats["events_by_user"]}
        assert by_user["alice"] == 2
        assert by_user["bob"] == 1

    def test_recent_failures(self, isolated_db):
        req = _make_request()
        audit_event(req, "auth_login_failed", reason="bad_password")
        audit_event(req, "auth_login_success")
        stats = get_audit_stats()
        assert len(stats["recent_failures"]) == 1
        assert stats["recent_failures"][0]["action"] == "auth_login_failed"


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


class TestAuditEndpoints:
    def test_get_events_authenticated(self):
        response = _client.get("/api/audit/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data

    def test_get_events_with_limit(self):
        response = _client.get("/api/audit/events?limit=5")
        assert response.status_code == 200
        assert response.json()["limit"] == 5

    def test_get_events_with_action_filter(self):
        response = _client.get("/api/audit/events?action=auth_")
        assert response.status_code == 200

    def test_get_stats(self):
        response = _client.get("/api/audit/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_events" in data
        assert "events_by_action" in data
        assert "events_by_user" in data
        assert "recent_failures" in data

    def test_get_events_invalid_limit(self):
        # limit=0 is invalid (ge=1), FastAPI returns 422
        response = _client.get("/api/audit/events?limit=0")
        assert response.status_code == 422

    def test_get_events_limit_exceeds_max(self):
        # limit=501 is invalid (le=500), FastAPI returns 422
        response = _client.get("/api/audit/events?limit=501")
        assert response.status_code == 422

    def test_get_events_with_until_filter(self):
        """Covers audit.py lines 243-244: 'until' parameter in get_audit_events."""
        _ensure_schema()
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO audit_events (timestamp, action, user, ip, details) VALUES (?, ?, ?, ?, ?)",
            ("2020-01-01T00:00:00", "old_action", "admin", "127.0.0.1", "{}"),
        )
        conn.commit()
        conn.close()

        result = get_audit_events(until="2020-06-01T00:00:00")
        actions = [e["action"] for e in result["events"]]
        assert "old_action" in actions
        # Events after the until date should not be included
        result2 = get_audit_events(until="2019-01-01T00:00:00")
        actions2 = [e["action"] for e in result2["events"]]
        assert "old_action" not in actions2

    def test_get_events_with_invalid_json_details(self):
        """Covers audit.py lines 269-270: JSONDecodeError fallback to empty dict."""
        _ensure_schema()
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO audit_events (timestamp, action, user, ip, details) VALUES (?, ?, ?, ?, ?)",
            ("2025-01-01T12:00:00", "corrupt_event", "admin", "127.0.0.1", "NOT_VALID_JSON"),
        )
        conn.commit()
        conn.close()

        result = get_audit_events(action_filter="corrupt_event")
        assert len(result["events"]) == 1
        # details should fall back to empty dict on JSON parse error
        assert result["events"][0]["details"] == {}

    def test_init_db_double_checked_locking(self):
        """Covers audit.py line 63: double-checked locking inside _DB_LOCK."""
        import app.core.audit as audit_module

        # To trigger line 63 (inner check inside the lock), we need _DB_INITIALIZED
        # to be False when we enter the lock, but True by the time we check again.
        # We simulate this by: setting _DB_INITIALIZED=True before calling _ensure_schema,
        # which means the outer check (line 59) passes, but we patch the lock context
        # so that inside the lock _DB_INITIALIZED is still True (line 62 check).
        original = audit_module._DB_INITIALIZED
        try:
            # Ensure schema is initialized
            audit_module._DB_INITIALIZED = True
            # Calling _ensure_schema with _DB_INITIALIZED=True hits line 59 and returns
            audit_module._ensure_schema()
            assert audit_module._DB_INITIALIZED is True

            # Now simulate the race: _DB_INITIALIZED is True when we enter the lock
            # by patching _DB_LOCK to execute the body and then check line 62
            audit_module._DB_INITIALIZED = False
            # Set it True again inside a thread to simulate race condition
            # We do this by patching: set True right before the lock body runs
            original_lock = audit_module._DB_LOCK

            class FakeLock:
                def __enter__(self):
                    # Simulate another thread completing init before we get the lock
                    audit_module._DB_INITIALIZED = True
                    return self

                def __exit__(self, *args):
                    return False

            audit_module._DB_LOCK = FakeLock()
            audit_module._ensure_schema()  # Should hit line 62 and return
            audit_module._DB_LOCK = original_lock
        finally:
            audit_module._DB_INITIALIZED = original
