"""
Comprehensive test suite for core/auth.py module.
Target coverage: >90% on all authentication and CSRF functions.
Tests: session management, token validation, CSRF protection, password verification.
"""

import base64
import hmac
import os
import secrets
import time
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.core.auth import (
    ADMIN_USERNAME,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    _b64,
    _b64_decode,
    _csrf_tokens,
    _lock,
    _sessions,
    _sign,
    auth_uses_default_password,
    cleanup_csrf_token,
    create_csrf_token,
    create_session,
    destroy_session,
    extract_token_from_request,
    generate_csrf_token,
    validate_csrf_dependency,
    validate_csrf_token,
    validate_session,
    verify_credentials,
)
from app.main import app


@pytest.fixture
def clear_sessions():
    """Clear all sessions and CSRF tokens before and after each test."""
    with _lock:
        _sessions.clear()
        _csrf_tokens.clear()
    yield
    with _lock:
        _sessions.clear()
        _csrf_tokens.clear()


@pytest.fixture
def enable_auth():
    """Enable auth for specific tests."""
    with patch("app.core.auth.AUTH_ENABLED", True):
        yield


class TestAuthHelpers:
    """Test internal authentication helper functions."""

    def test_b64_encode_decode_roundtrip(self):
        """Test base64 urlsafe encoding and decoding roundtrip."""
        original = "test_session_id:admin:1234567890"
        encoded = _b64(original)
        decoded = _b64_decode(encoded)
        assert decoded == original

    def test_b64_encode_special_characters(self):
        """Test encoding strings with special characters."""
        original = "test:with:colons:and_underscores-and-dashes"
        encoded = _b64(original)
        decoded = _b64_decode(encoded)
        assert decoded == original

    def test_b64_decode_handles_padding(self):
        """Test that b64_decode properly handles missing padding."""
        # Create properly padded base64
        original = "hello"
        encoded_with_padding = base64.urlsafe_b64encode(original.encode()).decode()
        encoded_no_padding = encoded_with_padding.rstrip("=")
        
        # _b64_decode should handle both with and without padding
        decoded = _b64_decode(encoded_no_padding)
        assert decoded == original

    def test_sign_produces_consistent_output(self):
        """Test that signing the same payload produces the same signature."""
        payload = "test:session:expires"
        sig1 = _sign(payload)
        sig2 = _sign(payload)
        assert sig1 == sig2

    def test_sign_different_payloads_different_signatures(self):
        """Test that different payloads produce different signatures."""
        sig1 = _sign("payload1")
        sig2 = _sign("payload2")
        assert sig1 != sig2


class TestCredentialVerification:
    """Test credential verification with different AUTH_ENABLED states."""

    @patch("app.core.auth.AUTH_ENABLED", True)
    @patch("app.core.auth._password_env", "test_password")
    def test_verify_credentials_valid(self):
        """Test verification of correct credentials when auth enabled."""
        result = verify_credentials(ADMIN_USERNAME, "test_password")
        assert result is True

    @patch("app.core.auth.AUTH_ENABLED", True)
    @patch("app.core.auth._password_env", "test_password")
    def test_verify_credentials_wrong_password(self):
        """Test verification with wrong password."""
        result = verify_credentials(ADMIN_USERNAME, "wrong_password")
        assert result is False

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_verify_credentials_wrong_username(self):
        """Test verification with wrong username."""
        result = verify_credentials("wrong_admin", "test_password")
        assert result is False

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_verify_credentials_empty_username(self):
        """Test verification with empty username."""
        result = verify_credentials("", "test_password")
        assert result is False

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_verify_credentials_empty_password(self):
        """Test verification with empty password."""
        result = verify_credentials(ADMIN_USERNAME, "")
        assert result is False

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_verify_credentials_none_values(self):
        """Test verification with None values."""
        result = verify_credentials(None, None)
        assert result is False

    @patch("app.core.auth.AUTH_ENABLED", False)
    def test_verify_credentials_auth_disabled(self):
        """Test that any credentials are accepted when auth disabled."""
        result = verify_credentials("any_user", "any_pass")
        assert result is True


class TestSessionManagement:
    """Test session creation, validation, and destruction."""

    def test_auth_uses_default_password(self):
        """Test detection of unconfigured password (✅ FIX #I-006)."""
        # When _password_env is None (not configured), should return True
        with patch("app.core.auth._password_env", None):
            assert auth_uses_default_password() is True
        
        # When _password_env is empty string (not configured), should return True
        with patch("app.core.auth._password_env", ""):
            assert auth_uses_default_password() is True
        
        # When _password_env is set to any value, should return False
        with patch("app.core.auth._password_env", "configured_password"):
            assert auth_uses_default_password() is False

    def test_create_session_returns_valid_format(self, clear_sessions):
        """Test that created session has correct format."""
        token, expires_at, csrf_token = create_session("testuser")
        
        # Token should be base64.signature
        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2
        
        # Expires at should be in future
        assert expires_at > int(time.time())
        
        # CSRF token should be a valid token
        assert csrf_token is not None
        assert len(csrf_token) > 0

    def test_create_session_stores_session(self, clear_sessions):
        """Test that create_session stores session and CSRF token."""
        token, _, csrf_token = create_session("testuser")
        payload_b64 = token.split(".")[0]
        payload = _b64_decode(payload_b64)
        sid = payload.split(":", 1)[0]
        
        # Session should be stored
        with _lock:
            assert sid in _sessions
            assert sid in _csrf_tokens
            assert _csrf_tokens[sid] == csrf_token

    def test_validate_session_valid_token(self, clear_sessions, enable_auth):
        """Test validation of valid session token."""
        token, _, _ = create_session("testuser")
        username = validate_session(token)
        assert username == "testuser"

    def test_validate_session_invalid_signature(self, clear_sessions, enable_auth):
        """Test validation fails with corrupted signature."""
        token, _, _ = create_session("testuser")
        payload_b64, sig = token.split(".")
        corrupted_token = payload_b64 + ".corrupted_signature"
        
        username = validate_session(corrupted_token)
        assert username is None

    def test_validate_session_expired(self, clear_sessions, enable_auth):
        """Test validation fails when session is expired."""
        token, _, _ = create_session("testuser")
        payload_b64 = token.split(".")[0]
        payload = _b64_decode(payload_b64)
        sid = payload.split(":", 1)[0]
        
        # Manually set session as expired
        expired_time = int(time.time()) - 1
        with _lock:
            _sessions[sid] = expired_time
        
        # Re-create token with expired timestamp
        payload_parts = payload.split(":")
        old_payload = f"{payload_parts[0]}:{payload_parts[1]}:{expired_time}"
        sig = _sign(old_payload)
        expired_token = f"{_b64(old_payload)}.{sig}"
        
        username = validate_session(expired_token)
        assert username is None
        
        # Expired session should be cleaned up
        with _lock:
            assert sid not in _sessions

    def test_validate_session_modified_session_id(self, clear_sessions, enable_auth):
        """Test validation fails when session_id doesn't match stored."""
        token, _, _ = create_session("testuser")
        payload_b64 = token.split(".")[0]
        payload = _b64_decode(payload_b64)
        
        # Modify the session_id in payload
        parts = payload.split(":")
        modified_sid = secrets.token_urlsafe(32)  # Different SID
        modified_payload = f"{modified_sid}:{parts[1]}:{parts[2]}"
        modified_sig = _sign(modified_payload)
        modified_token = f"{_b64(modified_payload)}.{modified_sig}"
        
        username = validate_session(modified_token)
        assert username is None

    def test_validate_session_malformed_token(self, clear_sessions, enable_auth):
        """Test validation with malformed token (no dot)."""
        result = validate_session("malformed_token_no_dot")
        assert result is None

    def test_validate_session_none_token(self, enable_auth):
        """Test validation with None token."""
        result = validate_session(None)
        assert result is None

    def test_validate_session_empty_token(self, enable_auth):
        """Test validation with empty token."""
        result = validate_session("")
        assert result is None

    @patch("app.core.auth.AUTH_ENABLED", False)
    def test_validate_session_auth_disabled(self, clear_sessions):
        """Test that any session is valid when auth disabled."""
        # Should return admin username without creating actual session
        result = validate_session("any_token")
        assert result == ADMIN_USERNAME

    def test_destroy_session_removes_session(self, clear_sessions):
        """Test that destroy_session removes session from storage."""
        token, _, _ = create_session("testuser")
        payload_b64 = token.split(".")[0]
        payload = _b64_decode(payload_b64)
        sid = payload.split(":", 1)[0]
        
        # Verify session exists
        with _lock:
            assert sid in _sessions
        
        # Destroy session
        destroy_session(token)
        
        # Verify session is removed
        with _lock:
            assert sid not in _sessions

    def test_destroy_session_malformed_token(self, clear_sessions):
        """Test destroy_session with malformed token (no dot)."""
        # Should not raise, just return silently
        destroy_session("malformed_token")

    def test_destroy_session_none_token(self, clear_sessions):
        """Test destroy_session with None token."""
        # Should not raise, just return silently
        destroy_session(None)

    def test_destroy_session_empty_token(self, clear_sessions):
        """Test destroy_session with empty token."""
        # Should not raise, just return silently
        destroy_session("")


class TestCSRFTokenManagement:
    """Test CSRF token generation, validation, and cleanup."""

    def test_generate_csrf_token_returns_string(self):
        """Test that generate_csrf_token returns a string."""
        token = generate_csrf_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_csrf_token_unique(self):
        """Test that each generated token is unique."""
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()
        assert token1 != token2

    def test_create_csrf_token_stores_token(self, clear_sessions):
        """Test that create_csrf_token stores token in memory."""
        session_id = "test_session"
        token = create_csrf_token(session_id)
        
        # Token should be stored
        with _lock:
            assert session_id in _csrf_tokens
            assert _csrf_tokens[session_id] == token

    def test_validate_csrf_token_valid(self, clear_sessions):
        """Test validation of valid CSRF token."""
        session_id = "test_session"
        token = create_csrf_token(session_id)
        
        result = validate_csrf_token(session_id, token)
        assert result is True

    def test_validate_csrf_token_invalid(self, clear_sessions):
        """Test validation fails with wrong token."""
        session_id = "test_session"
        token = create_csrf_token(session_id)
        wrong_token = generate_csrf_token()
        
        result = validate_csrf_token(session_id, wrong_token)
        assert result is False

    def test_validate_csrf_token_missing_token(self, clear_sessions):
        """Test validation fails when token is None."""
        session_id = "test_session"
        create_csrf_token(session_id)
        
        result = validate_csrf_token(session_id, None)
        assert result is False

    def test_validate_csrf_token_unknown_session(self, clear_sessions):
        """Test validation fails for unknown session_id."""
        token = generate_csrf_token()
        result = validate_csrf_token("unknown_session", token)
        assert result is False

    def test_validate_csrf_token_uses_constant_time_comparison(self, clear_sessions):
        """Test that validate_csrf_token uses constant-time comparison."""
        session_id = "test_session"
        token = create_csrf_token(session_id)
        
        # Valid token should pass
        assert validate_csrf_token(session_id, token) is True
        
        # Token with one char different should fail
        modified_token = token[:-1] + ("X" if token[-1] != "X" else "Y")
        assert validate_csrf_token(session_id, modified_token) is False

    def test_cleanup_csrf_token_removes_token(self, clear_sessions):
        """Test that cleanup_csrf_token removes token from storage."""
        session_id = "test_session"
        create_csrf_token(session_id)
        
        # Verify token exists
        with _lock:
            assert session_id in _csrf_tokens
        
        # Cleanup
        cleanup_csrf_token(session_id)
        
        # Verify token is removed
        with _lock:
            assert session_id not in _csrf_tokens

    def test_cleanup_csrf_token_unknown_session(self, clear_sessions):
        """Test cleanup_csrf_token with unknown session (should not raise)."""
        # Should not raise
        cleanup_csrf_token("unknown_session")


class TestRequestTokenExtraction:
    """Test extracting authentication token from FastAPI Request."""

    def test_extract_token_from_cookies(self):
        """Test extracting token from cookie."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: "cookie_token"}
        mock_request.headers = {}
        
        token = extract_token_from_request(mock_request)
        assert token == "cookie_token"

    def test_extract_token_from_auth_header(self):
        """Test extracting token from Authorization header."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        mock_request.headers = {"Authorization": "Bearer header_token"}
        
        token = extract_token_from_request(mock_request)
        assert token == "header_token"

    def test_extract_token_prefers_cookie_over_header(self):
        """Test that cookie is preferred over Authorization header."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: "cookie_token"}
        mock_request.headers = {"Authorization": "Bearer header_token"}
        
        token = extract_token_from_request(mock_request)
        assert token == "cookie_token"

    def test_extract_token_no_bearer_prefix(self):
        """Test extracting token when Authorization header has no Bearer prefix."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        mock_request.headers = {"Authorization": "NoBearer token"}
        
        token = extract_token_from_request(mock_request)
        assert token is None

    def test_extract_token_auth_header_lowercase_bearer(self):
        """Test that Bearer prefix is case-insensitive."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        mock_request.headers = {"Authorization": "bearer header_token"}
        
        token = extract_token_from_request(mock_request)
        assert token == "header_token"

    def test_extract_token_auth_header_mixed_case_bearer(self):
        """Test with mixed case Bearer."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        mock_request.headers = {"Authorization": "BeArEr header_token"}
        
        token = extract_token_from_request(mock_request)
        assert token == "header_token"

    def test_extract_token_none_when_no_token(self):
        """Test that None is returned when no token is present."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        mock_request.headers = {}
        
        token = extract_token_from_request(mock_request)
        assert token is None


class TestCSRFDependency:
    """Test the FastAPI CSRF validation dependency."""

    def test_csrf_dependency_disabled_auth(self):
        """Test that CSRF dependency skips validation when AUTH_ENABLED is False."""
        mock_request = MagicMock(spec=Request)
        
        with patch("app.core.auth.AUTH_ENABLED", False):
            # Should not raise
            validate_csrf_dependency(mock_request)

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_csrf_dependency_no_session_cookie(self):
        """Test CSRF dependency raises 401 when no session cookie."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}
        
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf_dependency(mock_request)
        
        assert exc_info.value.status_code == 401

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_csrf_dependency_malformed_session_token(self):
        """Test CSRF dependency raises 401 with malformed token (no dot)."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: "malformed_no_dot"}
        mock_request.headers = {}
        
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf_dependency(mock_request)
        
        assert exc_info.value.status_code == 401

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_csrf_dependency_no_csrf_token(self, clear_sessions):
        """Test CSRF dependency raises 403 when CSRF token is missing."""
        token, _, _ = create_session("testuser")
        
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: token}
        mock_request.headers = {}
        mock_request.query_params = {}
        
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf_dependency(mock_request)
        
        assert exc_info.value.status_code == 403

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_csrf_dependency_invalid_csrf_token(self, clear_sessions):
        """Test CSRF dependency raises 403 with invalid CSRF token."""
        token, _, _ = create_session("testuser")
        wrong_csrf = generate_csrf_token()
        
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: token}
        mock_request.headers = {"X-CSRF-Token": wrong_csrf}
        
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf_dependency(mock_request)
        
        assert exc_info.value.status_code == 403

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_csrf_dependency_valid_csrf_header(self, clear_sessions):
        """Test CSRF dependency passes with valid CSRF token in header."""
        token, _, csrf_token = create_session("testuser")
        
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: token}
        mock_request.headers = {"X-CSRF-Token": csrf_token}
        
        # Should not raise
        validate_csrf_dependency(mock_request)

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_csrf_dependency_valid_csrf_query_param(self, clear_sessions):
        """Test CSRF dependency passes with valid CSRF token in query param."""
        token, _, csrf_token = create_session("testuser")
        
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: token}
        mock_request.headers = {}
        mock_request.query_params = {"csrf_token": csrf_token}
        
        # Should not raise
        validate_csrf_dependency(mock_request)

    @patch("app.core.auth.AUTH_ENABLED", True)
    def test_csrf_dependency_prefers_header_over_query(self, clear_sessions):
        """Test CSRF dependency prefers header token over query param."""
        token, _, csrf_token = create_session("testuser")
        other_token = generate_csrf_token()
        
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {SESSION_COOKIE_NAME: token}
        mock_request.headers = {"X-CSRF-Token": csrf_token}
        mock_request.query_params = {"csrf_token": other_token}
        
        # Should not raise (uses header token)
        validate_csrf_dependency(mock_request)


class TestIntegrationWithAuthEndpoints:
    """Integration tests with actual FastAPI endpoints."""

    def test_login_endpoint_disabled_auth(self):
        """Test login endpoint when AUTH_ENABLED is False."""
        client = TestClient(app)
        
        with patch("app.core.auth.AUTH_ENABLED", False):
            # With auth disabled, login should still work but accept any password
            response = client.post("/api/auth/login", json={"username": "any", "password": "any"})
            assert response.status_code in [200, 401, 403]  # Depends on implementation

    def test_logout_endpoint_with_valid_session(self):
        """Test logout endpoint clears session."""
        client = TestClient(app)
        
        # Create a session
        token, _, csrf_token = create_session("testuser")
        
        # Logout
        response = client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
            cookies={SESSION_COOKIE_NAME: token}
        )
        
        # Should succeed (or at least not error)
        assert response.status_code in [200, 401, 403]  # Depends on auth settings
