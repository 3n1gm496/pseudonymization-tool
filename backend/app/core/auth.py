import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Optional, Tuple

# Lazy import to avoid circular dependency
_config_cache = None


def _get_config():
    """Lazy-load config to avoid circular imports."""
    global _config_cache
    if _config_cache is None:
        from app.core.profiles import get_config

        _config_cache = get_config()
    return _config_cache


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


SESSION_COOKIE_NAME = os.environ.get("AUTH_SESSION_COOKIE", "pseudonymizer_session")
SESSION_TTL_SECONDS = int(os.environ.get("AUTH_SESSION_TTL_SECONDS", "28800"))
ADMIN_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = "admin123!"

# Get cookie secure flag from deployment profile
SESSION_COOKIE_SECURE = _get_config().cookie_secure

# Get auth enabled flag from deployment profile (no pytest check inline)
AUTH_ENABLED = _get_config().auth_enabled

_secret = os.environ.get("AUTH_SECRET") or secrets.token_urlsafe(48)
_password_env = os.environ.get("AUTH_PASSWORD", DEFAULT_ADMIN_PASSWORD)

_sessions = {}
_csrf_tokens = {}  # ✅ FIX #C3: CSRF token storage (session_id -> csrf_token)
_lock = threading.Lock()


def auth_uses_default_password() -> bool:
    return _password_env == DEFAULT_ADMIN_PASSWORD


def _sign(payload: str) -> str:
    digest = hmac.new(_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _b64(data: str) -> str:
    return base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8").rstrip("=")


def _b64_decode(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8")).decode("utf-8")


def verify_credentials(username: str, password: str) -> bool:
    if not AUTH_ENABLED:
        return True
    return hmac.compare_digest(username or "", ADMIN_USERNAME) and hmac.compare_digest(password or "", _password_env)


def create_session(username: str) -> Tuple[str, int, str]:
    sid = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{sid}:{username}:{expires_at}"
    signature = _sign(payload)
    token = f"{_b64(payload)}.{signature}"
    csrf_token = generate_csrf_token()
    with _lock:
        _sessions[sid] = expires_at
        # ✅ FIX: Generate CSRF token with session
        _csrf_tokens[sid] = csrf_token
    return token, expires_at, csrf_token


def validate_session(token: Optional[str]) -> Optional[str]:
    if not AUTH_ENABLED:
        return ADMIN_USERNAME
    if not token or "." not in token:
        return None
    try:
        payload_b64, signature = token.split(".", 1)
        payload = _b64_decode(payload_b64)
        expected_sig = _sign(payload)
        if not hmac.compare_digest(signature, expected_sig):
            return None
        sid, username, expires_raw = payload.split(":", 2)
        expires_at = int(expires_raw)
        now = int(time.time())
        if now >= expires_at:
            # ✅ FIX: Remove expired session from memory to prevent memory leak
            with _lock:
                _sessions.pop(sid, None)
            return None
        with _lock:
            stored_exp = _sessions.get(sid)
            if stored_exp is None or stored_exp != expires_at:
                return None
        return username
    except Exception:
        return None


def destroy_session(token: Optional[str]) -> None:
    if not token or "." not in token:
        return
    try:
        payload_b64 = token.split(".", 1)[0]
        payload = _b64_decode(payload_b64)
        sid = payload.split(":", 1)[0]
        with _lock:
            _sessions.pop(sid, None)
    except Exception:
        return


def extract_token_from_request(request) -> Optional[str]:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


# ─── CSRF Protection (FIX #C3) ───────────────────────────────────────────────


def generate_csrf_token() -> str:
    """Generate cryptographically secure CSRF token (32 bytes)."""
    return secrets.token_urlsafe(32)


def create_csrf_token(session_id: str) -> str:
    """
    Create and store CSRF token for a given session.
    Returns the token to be sent to client (readable cookie).
    """
    csrf_token = generate_csrf_token()
    with _lock:
        _csrf_tokens[session_id] = csrf_token
    return csrf_token


def validate_csrf_token(session_id: str, provided_token: Optional[str]) -> bool:
    """
    Validate CSRF token against stored token for session.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not provided_token:
        return False
    
    with _lock:
        if session_id not in _csrf_tokens:
            return False
        stored_token = _csrf_tokens[session_id]
    
    # Constant-time comparison
    return hmac.compare_digest(stored_token, provided_token)


def cleanup_csrf_token(session_id: str) -> None:
    """Remove CSRF token when session is destroyed."""
    with _lock:
        _csrf_tokens.pop(session_id, None)


def validate_csrf_dependency(
    request: "Request",  # type: ignore
) -> None:
    """
    FastAPI dependency for CSRF validation.
    
    Usage in endpoints:
        @router.post(..., dependencies=[Depends(validate_csrf_dependency)])
        async def endpoint(...):
            ...
    
    The dependency extracts csrf_token from:
    1. X-CSRF-Token header (recommended)
    2. csrf_token query parameter (fallback)
    
    Note: Skips validation when AUTH_ENABLED is False (e.g., in tests)
    """
    import logging
    from fastapi import Header, HTTPException
    
    logger = logging.getLogger(__name__)
    
    # ✅ FIX: Skip CSRF validation when authentication is disabled (e.g., dev/test mode)
    if not AUTH_ENABLED:
        return  # No auth required, no CSRF check needed
    
    # Get CSRF token from either header or query
    csrf_from_header = request.headers.get("X-CSRF-Token")
    csrf_from_query = request.query_params.get("csrf_token")
    provided_csrf = csrf_from_header or csrf_from_query
    
    # Get session ID from cookie
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_cookie:
        logger.warning("CSRF validation failed: no session cookie")
        raise HTTPException(status_code=401, detail="No active session")
    
    # Extract session ID (format: base64_payload.signature)
    if "." not in session_cookie:
        logger.warning("CSRF validation failed: invalid session token format")
        raise HTTPException(status_code=401, detail="Invalid session")
    
    try:
        payload_b64 = session_cookie.split(".", 1)[0]
        payload = _b64_decode(payload_b64)
        session_id = payload.split(":", 1)[0]
    except Exception as e:
        logger.warning("CSRF validation failed: could not extract session_id: %s", e)
        raise HTTPException(status_code=401, detail="Invalid session")
    
    # Validate CSRF token
    if not validate_csrf_token(session_id, provided_csrf):
        logger.warning(
            "CSRF validation failed: sid=%s (%s), provided_token_length=%s",
            session_id[:8] if session_id else "unknown",
            "valid" if session_id in _csrf_tokens else "unknown",
            len(provided_csrf) if provided_csrf else 0
        )
        raise HTTPException(status_code=403, detail="CSRF token invalid or missing")

