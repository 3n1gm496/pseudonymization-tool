import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

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
# ✅ FIX #I-006: Remove hardcoded default password — must be explicitly configured
DEFAULT_ADMIN_PASSWORD = None  # Deprecated: no longer used in runtime

# Get cookie secure flag from deployment profile
SESSION_COOKIE_SECURE = _get_config().cookie_secure

# Get auth enabled flag from deployment profile (no pytest check inline)
AUTH_ENABLED = _get_config().auth_enabled


def _load_or_create_secret() -> Tuple[str, bool]:
    """
    ✅ FIX #I-006: Persist AUTH_SECRET to file to survive container restarts.
    Returns: (secret_value, was_from_env_or_file)
    """
    # Priority 1: Environment variable (always wins)
    if os.environ.get("AUTH_SECRET"):
        return os.environ.get("AUTH_SECRET"), True
    
    # Priority 2: Persisted file in /tmp (survives container unless ephemeral)
    secret_file = "/tmp/auth_secret.txt"
    if os.path.exists(secret_file):
        try:
            with open(secret_file, "r") as f:
                persisted = f.read().strip()
            if persisted and len(persisted) >= 32:
                return persisted, True
        except Exception:
            pass
    
    # Priority 3: Generate and persist
    generated = secrets.token_urlsafe(48)
    try:
        os.makedirs("/tmp", exist_ok=True)
        with open(secret_file, "w") as f:
            f.write(generated)
        os.chmod(secret_file, 0o600)  # Read-only by app
    except Exception:
        pass  # If writing fails, use generated secret in-memory only
    
    return generated, False


_secret, _secret_from_env = _load_or_create_secret()
_password_env = os.environ.get("AUTH_PASSWORD")  # No default fallback — must be explicit

_sessions = {}
_csrf_tokens = {}  # ✅ FIX #C3: CSRF token storage (session_id -> csrf_token)
_lock = threading.Lock()
_redis_client_cached = None
_redis_last_check = 0.0
_REDIS_RETRY_INTERVAL_SECONDS = 5.0


def _get_redis_client():
    global _redis_client_cached, _redis_last_check

    now = time.time()
    if _redis_client_cached is not None:
        return _redis_client_cached
    if now - _redis_last_check < _REDIS_RETRY_INTERVAL_SECONDS:
        return None

    _redis_last_check = now
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    try:
        from redis import Redis

        client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=0.3,
            socket_connect_timeout=0.3,
            retry_on_timeout=False,
        )
        client.ping()
        _redis_client_cached = client
        return client
    except Exception:
        _redis_client_cached = None
        return None


def _store_session(sid: str, username: str, expires_at: int, csrf_token: str) -> None:
    redis_client = _get_redis_client()
    if redis_client:
        ttl = max(1, expires_at - int(time.time()))
        redis_client.setex(
            f"auth:session:{sid}",
            ttl,
            json.dumps({"username": username, "expires_at": expires_at}),
        )
        redis_client.setex(f"auth:csrf:{sid}", ttl, csrf_token)
        return

    with _lock:
        _sessions[sid] = expires_at
        _csrf_tokens[sid] = csrf_token


def _get_session_expires(sid: str) -> Optional[int]:
    redis_client = _get_redis_client()
    if redis_client:
        raw = redis_client.get(f"auth:session:{sid}")
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return int(payload.get("expires_at", 0))
        except Exception:
            return None

    with _lock:
        return _sessions.get(sid)


def _delete_session_and_csrf(sid: str) -> None:
    redis_client = _get_redis_client()
    if redis_client:
        redis_client.delete(f"auth:session:{sid}")
        redis_client.delete(f"auth:csrf:{sid}")
        return

    with _lock:
        _sessions.pop(sid, None)
        _csrf_tokens.pop(sid, None)


def _get_csrf_token(sid: str) -> Optional[str]:
    redis_client = _get_redis_client()
    if redis_client:
        return redis_client.get(f"auth:csrf:{sid}")

    with _lock:
        return _csrf_tokens.get(sid)


def _set_csrf_token(sid: str, token: str) -> None:
    redis_client = _get_redis_client()
    if redis_client:
        expires_at = _get_session_expires(sid)
        ttl = max(1, (expires_at or int(time.time()) + SESSION_TTL_SECONDS) - int(time.time()))
        redis_client.setex(f"auth:csrf:{sid}", ttl, token)
        return

    with _lock:
        _csrf_tokens[sid] = token


def auth_uses_default_password() -> bool:
    """✅ FIX #I-006: Returns True if AUTH_PASSWORD is not configured (dangerous)."""
    return _password_env is None or _password_env == ""


def auth_uses_ephemeral_secret() -> bool:
    """✅ FIX #I-006: True when AUTH_SECRET not configured and generated at runtime.
    
    In production, this should fail at startup to ensure secret is persisted.
    """
    return not _secret_from_env


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
    # ✅ FIX: Handle _password_env=None case (no password configured)
    if _password_env is None:
        return False  # Auth enabled but no password configured → deny access
    return hmac.compare_digest(username or "", ADMIN_USERNAME) and hmac.compare_digest(password or "", _password_env)


def create_session(username: str) -> Tuple[str, int, str]:
    sid = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{sid}:{username}:{expires_at}"
    signature = _sign(payload)
    token = f"{_b64(payload)}.{signature}"
    csrf_token = generate_csrf_token()
    _store_session(sid, username, expires_at, csrf_token)
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
            _delete_session_and_csrf(sid)
            return None
        stored_exp = _get_session_expires(sid)
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
        _delete_session_and_csrf(sid)
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
    _set_csrf_token(session_id, csrf_token)
    return csrf_token


def validate_csrf_token(session_id: str, provided_token: Optional[str]) -> bool:
    """
    Validate CSRF token against stored token for session.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not provided_token:
        return False
    
    stored_token = _get_csrf_token(session_id)
    if not stored_token:
        return False
    
    # Constant-time comparison
    return hmac.compare_digest(stored_token, provided_token)


def cleanup_csrf_token(session_id: str) -> None:
    """Remove CSRF token when session is destroyed."""
    redis_client = _get_redis_client()
    if redis_client:
        redis_client.delete(f"auth:csrf:{session_id}")
        return
    with _lock:
        _csrf_tokens.pop(session_id, None)


def validate_csrf_dependency(
    request: "Request",
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
            "valid" if _get_csrf_token(session_id) else "unknown",
            len(provided_csrf) if provided_csrf else 0
        )
        raise HTTPException(status_code=403, detail="CSRF token invalid or missing")

