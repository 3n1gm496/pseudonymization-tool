import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from typing import Optional, Tuple

from fastapi import Request

logger = logging.getLogger(__name__)

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
# No hardcoded default password — must be explicitly configured via AUTH_PASSWORD env var

# Get cookie secure flag from deployment profile
SESSION_COOKIE_SECURE = _get_config().cookie_secure

# Get auth enabled flag from deployment profile (no pytest check inline)
AUTH_ENABLED = _get_config().auth_enabled


def _get_secret_file_path() -> str:
    """
    Return the path for the persisted AUTH_SECRET file.

    Uses PSEUDONYMIZER_STATE_DIR (a persistent Docker volume in production)
    instead of /tmp (which is ephemeral and world-readable on some systems).
    Falls back to a temp-based path only if STATE_DIR is not configured.
    """
    state_dir = os.environ.get("PSEUDONYMIZER_STATE_DIR")
    if state_dir:
        return os.path.join(state_dir, ".auth_secret")
    # Fallback for local dev (no Docker volume configured)
    import tempfile

    return os.path.join(tempfile.gettempdir(), "pseudonymizer_batches", "state", ".auth_secret")


def _load_or_create_secret() -> Tuple[str, bool]:
    """
    Load or generate the AUTH_SECRET used for signing session tokens.

    Priority order:
      1. AUTH_SECRET environment variable (always wins — use in production)
      2. Persisted file in STATE_DIR (survives container restarts)
      3. Generate a new secret and persist it (first-run only)

    Returns: (secret_value, is_persistent)
      - is_persistent=True  → secret survives restarts (env var or file)
      - is_persistent=False → ephemeral secret (file write failed); sessions
                              will be invalidated on every restart
    """
    # Priority 1: Environment variable
    env_secret = os.environ.get("AUTH_SECRET")
    if env_secret and len(env_secret) >= 32:
        return env_secret, True

    # Priority 2: Persisted file in STATE_DIR
    secret_file = _get_secret_file_path()
    if os.path.exists(secret_file):
        try:
            with open(secret_file, "r", encoding="utf-8") as f:
                persisted = f.read().strip()
            if persisted and len(persisted) >= 32:
                return persisted, True
            logger.warning(
                "auth: secret file exists but content is too short (%d chars) — regenerating",
                len(persisted),
            )
        except OSError as exc:
            logger.warning("auth: could not read secret file %s: %s — regenerating", secret_file, exc)

    # Priority 3: Generate and persist
    generated = secrets.token_urlsafe(48)
    try:
        os.makedirs(os.path.dirname(secret_file), exist_ok=True)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(generated)
        os.chmod(secret_file, 0o600)
        logger.info("auth: generated and persisted new AUTH_SECRET to %s", secret_file)
        return generated, True
    except OSError as exc:
        logger.warning(
            "auth: could not persist secret to %s: %s — using ephemeral secret. "
            "Sessions will be invalidated on every restart.",
            secret_file,
            exc,
        )
        return generated, False


_secret, _secret_from_env = _load_or_create_secret()
_password_env = os.environ.get("AUTH_PASSWORD")  # No default fallback — must be explicit

_sessions: dict = {}
_csrf_tokens: dict = {}  # CSRF token storage (session_id -> csrf_token)
_lock = threading.Lock()

# Redis client cache — protected by _redis_lock to avoid race conditions
_redis_client_cached: Optional[object] = None
_redis_last_check: float = 0.0
_redis_lock = threading.Lock()
_REDIS_RETRY_INTERVAL_SECONDS = 5.0


def _get_redis_client():
    """
    Return a connected Redis client, or None if Redis is unavailable.

    Uses a dedicated lock (_redis_lock) to prevent race conditions on the
    cached client and last-check timestamp. Falls back gracefully to
    in-memory storage when Redis is not reachable.
    """
    global _redis_client_cached, _redis_last_check

    with _redis_lock:
        now = time.time()
        if _redis_client_cached is not None:
            return _redis_client_cached
        if now - _redis_last_check < _REDIS_RETRY_INTERVAL_SECONDS:
            return None

        _redis_last_check = now
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            # No REDIS_URL configured — use in-memory fallback silently
            return None

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
            logger.debug("auth: Redis connection established (%s)", redis_url.split("@")[-1])
            return client
        except Exception as exc:
            _redis_client_cached = None
            logger.debug("auth: Redis unavailable, using in-memory fallback: %s", exc)
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
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("auth: malformed session payload for sid=%s: %s", sid[:8], exc)
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


def get_csrf_token_for_session(token: Optional[str]) -> Optional[str]:
    """Retrieve the CSRF token associated with an existing session token.

    Used by /auth/me to include the CSRF token in the bootstrap response,
    so clients that already have a valid session cookie (e.g. after a page
    reload) can obtain their CSRF token without logging in again.

    Returns None if the token is invalid, expired, or has no CSRF entry.
    """
    if not AUTH_ENABLED:
        # When auth is disabled, no CSRF token is needed
        return None
    if not token or "." not in token:
        return None
    try:
        payload_b64 = token.split(".", 1)[0]
        payload = _b64_decode(payload_b64)
        sid = payload.split(":", 1)[0]
        return _get_csrf_token(sid)
    except Exception:
        return None


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
    """Returns True if AUTH_PASSWORD is not configured (dangerous in production)."""
    return _password_env is None or _password_env == ""  # nosec B105 — empty string check, not a hardcoded password


def auth_uses_ephemeral_secret() -> bool:
    """True when AUTH_SECRET is not configured and was generated at runtime.

    In production, AUTH_SECRET should be set via environment variable to ensure
    sessions survive container restarts.
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


def verify_credentials(username: str, password: str, auth_method: str = "local") -> Optional[str]:
    """
    Verifica le credenziali dell'utente.

    Ritorna il ruolo ('admin' o 'operator') se le credenziali sono valide,
    None altrimenti.

    Priorità in base al metodo scelto dall'utente (auth_method):
    - 'ldap':  Autentica tramite server LDAP (eDirectory/AD). Nessun fallback locale.
    - 'local': (default) Autentica tramite database locale SQLite + bcrypt.
               Fallback legacy su AUTH_USERNAME + AUTH_PASSWORD env vars.

    In caso di irraggiungibilità del server LDAP, il metodo 'ldap' ritorna None
    senza tentare l'autenticazione locale (fail-safe, Opzione X).
    """
    if not AUTH_ENABLED:
        return "admin"

    username_clean = (username or "").strip().lower()
    if not username_clean or not password:
        return None

    # ── Ramo LDAP: autenticazione aziendale tramite eDirectory/AD ────────────────
    if auth_method == "ldap":
        try:
            from app.core.ldap_auth import authenticate_ldap

            role = authenticate_ldap(username_clean, password)
            if role is not None:
                return role
        except Exception as exc:
            logger.warning("auth: errore nel modulo ldap_auth: %s", exc)
        # Opzione X: se LDAP non risponde o l'autenticazione fallisce,
        # NON si fa fallback al login locale. Si ritorna None.
        return None

    # ── Ramo Locale: autenticazione tramite database SQLite + bcrypt ────────────
    # Priorità 1: user_manager (SQLite con bcrypt)
    try:
        from app.core.user_manager import verify_credentials as um_verify

        role = um_verify(username_clean, password)
        if role is not None:
            return role
    except Exception as exc:
        logger.warning("auth: user_manager non disponibile, fallback legacy: %s", exc)

    # Priorità 2: fallback legacy (AUTH_USERNAME + AUTH_PASSWORD env vars)
    if _password_env is not None:
        if hmac.compare_digest(username_clean, ADMIN_USERNAME.lower()) and hmac.compare_digest(password, _password_env):
            return "admin"

    return None


def create_session(username: str) -> Tuple[str, int, str]:
    sid = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{sid}:{username}:{expires_at}"
    signature = _sign(payload)
    token = f"{_b64(payload)}.{signature}"
    csrf_token = generate_csrf_token()
    _store_session(sid, username, expires_at, csrf_token)
    return token, expires_at, csrf_token


def validate_session(token: Optional[str]) -> Optional[Tuple[str, str]]:
    """
    Valida un token di sessione.

    Ritorna (username, role) se la sessione è valida, None altrimenti.
    Il ruolo viene recuperato dal user_manager (SQLite) per riflettere
    eventuali modifiche ai ruoli avvenute dopo il login.
    """
    if not AUTH_ENABLED:
        # Quando l'auth è disabilitata, ritorna admin di default
        return (ADMIN_USERNAME, "admin")
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
        # Recupera il ruolo aggiornato dal user_manager
        try:
            from app.core.user_manager import get_user_role

            role = get_user_role(username)
            if role is None:
                # Utente non trovato nel DB (es. eliminato mentre loggato)
                # Fallback: ruolo admin per retrocompatibilità con utenti legacy
                role = "admin" if username == ADMIN_USERNAME else "operator"
        except Exception:
            role = "admin" if username == ADMIN_USERNAME else "operator"
        return (username, role)
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


def destroy_all_sessions() -> int:
    """
    Invalida tutte le sessioni attive (logout globale).

    Utile per:
    - Risposta a un incidente di sicurezza
    - Cambio password dell'admin
    - Revoca forzata di tutti gli accessi

    Restituisce il numero di sessioni invalidate.
    """
    redis_client = _get_redis_client()
    if redis_client:
        try:
            session_keys = redis_client.keys("auth:session:*")
            csrf_keys = redis_client.keys("auth:csrf:*")
            count = len(session_keys)
            if session_keys:
                redis_client.delete(*session_keys)
            if csrf_keys:
                redis_client.delete(*csrf_keys)
            logger.info("auth: destroyed all %d sessions (global logout)", count)
            return count
        except Exception as exc:
            logger.warning("auth: error during global logout via Redis: %s", exc)
            return 0

    with _lock:
        count = len(_sessions)
        _sessions.clear()
        _csrf_tokens.clear()
    logger.info("auth: destroyed all %d sessions (global logout, in-memory)", count)
    return count


def extract_token_from_request(request) -> Optional[str]:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


# ─── CSRF Protection ─────────────────────────────────────────────────────────


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
    request: Request,
) -> None:
    """
    FastAPI dependency for CSRF validation on mutating endpoints.

    Usage in endpoints:
        @router.post(..., dependencies=[Depends(validate_csrf_dependency)])
        async def endpoint(...):
            ...

    Extracts the CSRF token from:
      1. X-CSRF-Token header (recommended)
      2. csrf_token query parameter (fallback)

    Skips validation when AUTH_ENABLED is False (dev/test mode).
    """
    from fastapi import HTTPException

    if not AUTH_ENABLED:
        return

    csrf_from_header = request.headers.get("X-CSRF-Token")
    csrf_from_query = request.query_params.get("csrf_token")
    provided_csrf = csrf_from_header or csrf_from_query

    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_cookie:
        logger.warning("CSRF validation failed: no session cookie")
        raise HTTPException(status_code=401, detail="No active session")

    if "." not in session_cookie:
        logger.warning("CSRF validation failed: invalid session token format")
        raise HTTPException(status_code=401, detail="Invalid session")

    try:
        payload_b64 = session_cookie.split(".", 1)[0]
        payload = _b64_decode(payload_b64)
        session_id = payload.split(":", 1)[0]
    except Exception as exc:
        logger.warning("CSRF validation failed: could not extract session_id: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid session")

    if not validate_csrf_token(session_id, provided_csrf):
        logger.warning(
            "CSRF validation failed: sid=%s, stored=%s, provided_len=%s",
            session_id[:8] if session_id else "unknown",
            "present" if _get_csrf_token(session_id) else "missing",
            len(provided_csrf) if provided_csrf else 0,
        )
        raise HTTPException(status_code=403, detail="CSRF token invalid or missing")
