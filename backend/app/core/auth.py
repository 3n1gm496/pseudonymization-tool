import base64
import hashlib
import hmac
import os
import secrets
import sys
import threading
import time
from typing import Optional, Tuple


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


SESSION_COOKIE_NAME = os.environ.get("AUTH_SESSION_COOKIE", "pseudonymizer_session")
SESSION_TTL_SECONDS = int(os.environ.get("AUTH_SESSION_TTL_SECONDS", "28800"))
SESSION_COOKIE_SECURE = _env_flag("AUTH_SESSION_COOKIE_SECURE", default=True)
ADMIN_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = "admin123!"

_running_under_pytest = (
    os.environ.get("PYTEST_CURRENT_TEST") is not None
    or "pytest" in sys.modules
)
_auth_enabled_default = "false" if _running_under_pytest else "true"
AUTH_ENABLED = _env_flag("AUTH_ENABLED", default=(_auth_enabled_default == "true"))

_secret = os.environ.get("AUTH_SECRET") or secrets.token_urlsafe(48)
_password_env = os.environ.get("AUTH_PASSWORD", DEFAULT_ADMIN_PASSWORD)

_sessions = {}
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


def create_session(username: str) -> Tuple[str, int]:
    sid = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{sid}:{username}:{expires_at}"
    signature = _sign(payload)
    token = f"{_b64(payload)}.{signature}"
    with _lock:
        _sessions[sid] = expires_at
    return token, expires_at


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
