"""
Router API per health/readiness e autenticazione.
Separato dal router monolitico per ridurre blast radius e accoppiamento.
"""

import logging
from datetime import datetime, timezone

from app import __version__
from app.core.audit import audit_event
from app.core.auth import (
    ADMIN_USERNAME,
    AUTH_ENABLED,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_TTL_SECONDS,
    auth_uses_default_password,
    create_session,
    destroy_session,
    extract_token_from_request,
    get_csrf_token_for_session,
    validate_session,
    verify_credentials,
)
from app.core.config import CONFIG_DIR
from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# Helper functions moved to app.core.audit module


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "Local Pseudonymization Tool",
        "version": __version__,
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
        audit_event(request, "auth_login_failed", username=username)
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    token, expires_at, csrf_token = create_session(username or ADMIN_USERNAME)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="strict",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    # ✅ FIX: Return CSRF token in response header for frontend
    response.headers["X-CSRF-Token"] = csrf_token
    audit_event(request, "auth_login_success", username=username or ADMIN_USERNAME)
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
    # ✅ FIX: Delete cookie with all parameters to ensure browser recognizes it
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, path="/", secure=SESSION_COOKIE_SECURE, httponly=True, samesite="strict"
    )
    audit_event(request, "auth_logout")
    return {"ok": True}


@router.get("/auth/me")
async def auth_me(request: Request, response: Response):
    """Return current authentication status.

    Also includes the CSRF token in the X-CSRF-Token response header so that
    clients with an existing valid session cookie (e.g. after a page reload)
    can bootstrap their CSRF token without performing a full login.
    """
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

    # ✅ CSRF bootstrap: include the CSRF token so the frontend can restore it
    # after a page reload without requiring a new login.
    csrf_token = get_csrf_token_for_session(token)
    if csrf_token:
        response.headers["X-CSRF-Token"] = csrf_token

    return {
        "authenticated": True,
        "username": username,
        "auth_enabled": True,
        "default_password": auth_uses_default_password(),
    }
