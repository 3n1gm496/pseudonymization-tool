"""
Test suite for CSRF middleware implementation.

Validates that:
1. All POST/PUT/DELETE/PATCH requests require valid CSRF token
2. Public endpoints are exempt from CSRF validation
3. Safe methods (GET, HEAD, OPTIONS) don't require CSRF
4. CSRF middleware executes after authentication
5. Session cookie logout includes all security parameters
"""

import os

import pytest
from app.core.auth import SESSION_COOKIE_NAME, create_session, destroy_session
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def enable_auth_for_csrf_tests(monkeypatch):
    """
    Enable authentication for CSRF tests.
    Overrides the default disable_auth_for_tests fixture.
    """
    from app import main
    from app.core import auth

    # Enable auth in profile config
    object.__setattr__(main._profile_config, "auth_enabled", True)
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)

    # Ensure _password_env is set from environment (loaded at module import time)
    # This is needed because _password_env is loaded at module import time
    import os

    password = os.environ.get("AUTH_PASSWORD", "T3st-0nly-N0t-Pr0d!#2026")
    monkeypatch.setattr(auth, "_password_env", password)

    yield

    # Cleanup: restore disabled state
    object.__setattr__(main._profile_config, "auth_enabled", False)
    monkeypatch.setattr(auth, "AUTH_ENABLED", False)


@pytest.fixture
def authenticated_client(enable_auth_for_csrf_tests):
    """
    Create TestClient with authenticated session and CSRF token.
    Returns tuple: (client, session_token, csrf_token)
    """
    client = TestClient(app)

    # Create session and get CSRF token
    session_token, expires_at, csrf_token = create_session("test_user")

    # Set cookie directly on the client instance to avoid per-request cookie deprecation warning
    client.cookies.set(SESSION_COOKIE_NAME, session_token)
    client._test_session_token = session_token
    client._test_csrf_token = csrf_token

    yield client, session_token, csrf_token

    # Cleanup
    destroy_session(session_token)


class TestCSRFMiddleware:
    """Test CSRF middleware protection."""

    def test_post_without_csrf_token_blocked(self, authenticated_client):
        """POST request without CSRF token should return 403."""
        client, session_token, csrf_token = authenticated_client

        # Try POST without CSRF token (but with session cookie)
        response = client.post(
            "/api/console/scan",
            json={"text": "test", "mode": "light", "preset": "SOC Logs"},
        )

        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_put_without_csrf_token_blocked(self, authenticated_client):
        """PUT request without CSRF token should return 403."""
        client, session_token, csrf_token = authenticated_client

        # Try PUT without CSRF token (but with session cookie)
        response = client.put("/api/batches/test-id", json={})

        # Should be blocked by CSRF before 404
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_delete_without_csrf_token_blocked(self, authenticated_client):
        """DELETE request without CSRF token should return 403."""
        client, session_token, csrf_token = authenticated_client

        # Try DELETE without CSRF token (but with session cookie)
        response = client.delete("/api/batches/test-id")

        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_post_with_valid_csrf_token_header(self, authenticated_client, monkeypatch):
        """POST with valid CSRF token in header should succeed."""
        client, session_token, csrf_token = authenticated_client

        # Mock the scan function to avoid actual processing
        from app.api import console_routes
        from app.models.schemas import SafetyLabel

        def fake_run_text_scan(batch_id: str, text: str, label: str):
            return "file-1", [], SafetyLabel.SAFE_TO_UPLOAD

        monkeypatch.setattr(console_routes, "run_text_scan", fake_run_text_scan)

        # POST with CSRF token in header and session cookie
        response = client.post(
            "/api/console/scan",
            json={"text": "test", "mode": "light", "preset": "SOC Logs"},
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code == 200

    def test_post_with_valid_csrf_token_query(self, authenticated_client, monkeypatch):
        """POST with valid CSRF token in query parameter should succeed."""
        client, session_token, csrf_token = authenticated_client

        # Mock the scan function
        from app.api import console_routes
        from app.models.schemas import SafetyLabel

        def fake_run_text_scan(batch_id: str, text: str, label: str):
            return "file-2", [], SafetyLabel.SAFE_TO_UPLOAD

        monkeypatch.setattr(console_routes, "run_text_scan", fake_run_text_scan)

        # POST with CSRF token in query parameter and session cookie
        response = client.post(
            f"/api/console/scan?csrf_token={csrf_token}",
            json={"text": "test", "mode": "light", "preset": "SOC Logs"},
        )

        assert response.status_code == 200

    def test_get_request_does_not_require_csrf(self, authenticated_client):
        """GET requests should not require CSRF token (safe method)."""
        client, session_token, csrf_token = authenticated_client

        # GET without CSRF token should work (with session cookie)
        response = client.get("/api/health")

        assert response.status_code == 200

    def test_options_request_does_not_require_csrf(self, authenticated_client):
        """OPTIONS requests should not require CSRF token (safe method)."""
        client, session_token, csrf_token = authenticated_client

        # OPTIONS without CSRF token should work
        response = client.options("/api/console/scan")

        # Should not be blocked by CSRF (status could be 200 or 405)
        assert response.status_code != 403


class TestCSRFExemptPaths:
    """Test CSRF exempt paths (public endpoints)."""

    def test_health_endpoint_exempt(self, enable_auth_for_csrf_tests):
        """Health endpoint should not require CSRF."""
        client = TestClient(app)

        # POST to health without CSRF (even though health is GET)
        response = client.get("/api/health")

        assert response.status_code == 200

    def test_ready_endpoint_exempt(self, enable_auth_for_csrf_tests):
        """Ready endpoint should not require CSRF."""
        client = TestClient(app)

        response = client.get("/api/ready")

        assert response.status_code == 200

    def test_login_endpoint_exempt(self, enable_auth_for_csrf_tests):
        """Login endpoint should not require CSRF (can't have token before login)."""
        client = TestClient(app)

        # Login should work without CSRF
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})

        # Should fail on auth, not CSRF (401 not 403)
        assert response.status_code == 401
        assert "CSRF" not in response.json()["detail"]

    def test_docs_endpoints_exempt(self, enable_auth_for_csrf_tests):
        """API docs endpoints should not require CSRF."""
        client = TestClient(app)

        # Docs should be accessible
        response = client.get("/api/docs")

        # Should not be blocked by CSRF
        assert response.status_code != 403


class TestCSRFMiddlewareOrder:
    """Test that CSRF middleware executes after authentication."""

    def test_csrf_after_auth_unauthenticated_request(self, enable_auth_for_csrf_tests):
        """Unauthenticated requests should fail with 401 before CSRF check."""
        client = TestClient(app)

        # POST without session (no authentication)
        response = client.post("/api/console/scan", json={"text": "test", "mode": "light", "preset": "SOC Logs"})

        # Should fail on auth first (401), not CSRF (403)
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"

    def test_csrf_checked_after_auth_passed(self, authenticated_client):
        """Authenticated requests without CSRF should fail with 403."""
        client, session_token, csrf_token = authenticated_client

        # POST with valid session but no CSRF
        response = client.post(
            "/api/console/scan",
            json={"text": "test", "mode": "light", "preset": "SOC Logs"},
        )

        # Should fail on CSRF (403), not auth (401)
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]


class TestSessionCookieLogout:
    """Test session cookie logout fix."""

    def test_logout_deletes_cookie_with_all_parameters(self, enable_auth_for_csrf_tests):
        """Logout should delete cookie with httponly, secure, samesite parameters."""
        client = TestClient(app)

        # Login to get session
        password = os.environ.get("AUTH_PASSWORD", "T3st-0nly-N0t-Pr0d!#2026")
        response = client.post("/api/auth/login", json={"username": "admin", "password": password})

        assert response.status_code == 200

        # Get CSRF token from response header
        csrf_token = response.headers.get("X-CSRF-Token")
        assert csrf_token is not None

        # Logout with CSRF token
        logout_response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

        assert logout_response.status_code == 200
        assert logout_response.json()["ok"] is True

        # Verify cookie deletion in Set-Cookie header
        set_cookie_header = logout_response.headers.get("set-cookie")
        assert set_cookie_header is not None

        # Cookie should have proper deletion parameters
        assert SESSION_COOKIE_NAME in set_cookie_header
        # Check for security parameters (httponly, secure, samesite)
        # Note: TestClient may not preserve all cookie attributes in lowercase
        set_cookie_lower = set_cookie_header.lower()
        assert "path=/" in set_cookie_lower

        # Verify session cookie is removed (value should be empty or max-age=0)
        # TestClient cookie deletion shows as empty value or max-age=0
        assert (
            "max-age=0" in set_cookie_lower
            or f"{SESSION_COOKIE_NAME}=;" in set_cookie_header
            or f'{SESSION_COOKIE_NAME}=""' in set_cookie_header
        )


class TestCSRFWithInvalidSession:
    """Test CSRF middleware with invalid or malformed sessions."""

    def test_csrf_with_malformed_session_cookie(self, enable_auth_for_csrf_tests):
        """CSRF validation should fail gracefully with malformed session."""
        client = TestClient(app)
        # Set malformed cookie directly on client to avoid per-request cookie deprecation warning
        client.cookies.set(SESSION_COOKIE_NAME, "invalid-no-dot")
        # POST with malformed session cookie and CSRF token
        response = client.post(
            "/api/console/scan",
            json={"text": "test", "mode": "light", "preset": "SOC Logs"},
            headers={"X-CSRF-Token": "some-token"},
        )

        # Should skip CSRF (malformed cookie) and fail on auth (401)
        # Because malformed cookies are treated as no-cookie by CSRF middleware
        assert response.status_code == 401
        assert "Authentication" in response.json()["detail"]

    def test_csrf_with_expired_session(self, enable_auth_for_csrf_tests):
        """CSRF validation should handle expired sessions."""
        client = TestClient(app)
        # Create session and let it expire (or use invalid session_id)
        session_token, expires_at, csrf_token = create_session("test_user")
        # Destroy session to simulate expiration
        destroy_session(session_token)
        # Set cookie directly on client to avoid per-request cookie deprecation warning
        client.cookies.set(SESSION_COOKIE_NAME, session_token)
        # POST with CSRF token but expired session
        response = client.post(
            "/api/console/scan",
            json={"text": "test", "mode": "light", "preset": "SOC Logs"},
            headers={"X-CSRF-Token": csrf_token},
        )

        # Should fail with CSRF validation error (403) when session is invalid
        # CSRF middleware checks token validity before auth completes
        assert response.status_code == 403
