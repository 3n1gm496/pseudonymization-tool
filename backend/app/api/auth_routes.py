"""
Router API per health/readiness e autenticazione.
Separato dal router monolitico per ridurre blast radius e accoppiamento.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import CONFIG_DIR
from app.core.auth import (
    AUTH_ENABLED,
    ADMIN_USERNAME,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_TTL_SECONDS,
    auth_uses_default_password,
    create_session,
    destroy_session,
    extract_token_from_request,
    validate_session,
    verify_credentials,
)


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if any(token in key_l for token in ("password", "passphrase", "secret", "token", "api_key", "bind_password")):
                continue
            cleaned[key] = _scrub_sensitive(item)
        return cleaned
    if isinstance(value, list):
        return [_scrub_sensitive(item) for item in value]
    return value


def _audit_event(request: Optional[Request], action: str, **details: Any) -> None:
    user = "anonymous"
    ip = "unknown"
    if request is not None:
        user = getattr(request.state, "auth_user", "anonymous")
        ip = request.client.host if request.client else "unknown"
    cleaned = _scrub_sensitive(details)
    logger.info("AUDIT action=%s user=%s ip=%s details=%s", action, user, ip, cleaned)


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "Local Pseudonymization Tool",
        "version": "4.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def ready_check():
    checks = {
        "config_dir": CONFIG_DIR.exists(),
        "dictionaries_dir": (CONFIG_DIR / "dictionaries").exists(),
    }
    ready = all(checks.values())
    return {
        "ready": ready,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/auth/login")
async def auth_login(req: dict, response: Response, request: Request):
    username = (req.get("username") or "").strip()
    password = req.get("password") or ""
    if not verify_credentials(username, password):
        _audit_event(request, "auth_login_failed", username=username)
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    token, expires_at = create_session(username or ADMIN_USERNAME)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="strict",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    _audit_event(request, "auth_login_success", username=username or ADMIN_USERNAME)
    return {
        "authenticated": True,
        "username": username or ADMIN_USERNAME,
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "auth_enabled": AUTH_ENABLED,
        "default_password": auth_uses_default_password(),
    }


@router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = extract_token_from_request(request)
    destroy_session(token)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    _audit_event(request, "auth_logout")
    return {"ok": True}


@router.get("/auth/me")
async def auth_me(request: Request):
    if not AUTH_ENABLED:
        return {
            "authenticated": True,
            "username": ADMIN_USERNAME,
            "auth_enabled": False,
            "default_password": auth_uses_default_password(),
        }

    token = extract_token_from_request(request)
    username = validate_session(token)
    if not username:
        raise HTTPException(status_code=401, detail="Non autenticato")
    return {
        "authenticated": True,
        "username": username,
        "auth_enabled": True,
        "default_password": auth_uses_default_password(),
    }
