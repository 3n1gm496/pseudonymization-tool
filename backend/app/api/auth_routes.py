"""
Router API per health/readiness e autenticazione.
Separato dal router monolitico per ridurre blast radius e accoppiamento.
"""

import logging
import time
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
    destroy_all_sessions,
    destroy_session,
    extract_token_from_request,
    get_csrf_token_for_session,
    validate_session,
    verify_credentials,
)
from app.core.config import CONFIG_DIR
from app.core.metrics import get_metrics_output
from app.core.rate_limit import enforce_rate_limit
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import Response as FastAPIResponse

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# Timestamp di avvio del server (usato per calcolare uptime)
_SERVER_START_TIME: float = time.time()

# Helper functions moved to app.core.audit module


@router.get("/health")
async def health_check():
    """
    Liveness probe: verifica che il processo sia in esecuzione.

    Risponde sempre 200 OK se il server è avviato.
    Usato da Docker HEALTHCHECK, Kubernetes liveness probe e load balancer.
    """
    uptime_seconds = int(time.time() - _SERVER_START_TIME)
    return {
        "status": "ok",
        "service": "Local Pseudonymization Tool",
        "version": __version__,
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def ready_check():
    """
    Readiness probe: verifica che il servizio sia pronto ad accettare traffico.

    Controlla:
    - Presenza della directory di configurazione
    - Presenza dei dizionari
    - Accessibilità della directory temporanea

    Risponde 200 se pronto, 503 se non pronto.
    Usato da Kubernetes readiness probe e health check del load balancer.
    """
    from app.core.config import TEMP_BASE_DIR

    checks = {
        "config_dir": CONFIG_DIR.exists(),
        "dictionaries_dir": (CONFIG_DIR / "dictionaries").exists(),
        "temp_dir": TEMP_BASE_DIR.exists() and TEMP_BASE_DIR.is_dir(),
    }
    ready = all(checks.values())
    status_code = 200 if ready else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content={
            "ready": ready,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/metrics")
async def metrics_endpoint():
    """
    Endpoint Prometheus metrics in formato text/plain 0.0.4.

    Espone metriche applicative per il monitoring:
    - pseudonymizer_scans_total: contatore scan completati per preset
    - pseudonymizer_applies_total: contatore apply completati
    - pseudonymizer_errors_total: contatore errori HTTP per status code ed endpoint
    - pseudonymizer_active_batches: gauge batch attivi in memoria
    - pseudonymizer_http_requests_total: contatore richieste HTTP

    Esentato da autenticazione e CSRF (configurato in main.py).
    Proteggere con firewall o nginx auth_basic in produzione se necessario.
    """
    content, content_type = get_metrics_output()
    return FastAPIResponse(content=content, media_type=content_type)


@router.post("/auth/login")
async def auth_login(req: dict, response: Response, request: Request):
    # Protezione brute-force: max 10 tentativi/minuto per IP.
    # Limite volutamente basso: un utente legittimo non ha mai bisogno
    # di più di 1-2 tentativi; 10 è già generoso.
    enforce_rate_limit(request, "auth_login", limit=10)
    username = (req.get("username") or "").strip()
    password = req.get("password") or ""
    role = verify_credentials(username, password)
    if role is None:
        audit_event(request, "auth_login_failed", username=username)
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    effective_username = username or ADMIN_USERNAME
    token, expires_at, csrf_token = create_session(effective_username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="strict",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    # Return CSRF token in response header for frontend
    response.headers["X-CSRF-Token"] = csrf_token
    audit_event(request, "auth_login_success", username=effective_username)
    return {
        "authenticated": True,
        "username": effective_username,
        "role": role,
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "auth_enabled": AUTH_ENABLED,
        "default_password": auth_uses_default_password(),
    }


@router.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = extract_token_from_request(request)
    destroy_session(token)
    # Delete cookie with all parameters to ensure browser recognizes it
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, path="/", secure=SESSION_COOKIE_SECURE, httponly=True, samesite="strict"
    )
    audit_event(request, "auth_logout")
    return {"ok": True}


@router.post("/auth/logout-all")
async def auth_logout_all(request: Request, response: Response):
    """
    Logout globale: invalida tutte le sessioni attive.

    Richiede autenticazione valida. Utile per rispondere a un incidente
    di sicurezza o per forzare il re-login di tutti i client attivi.
    Restituisce il numero di sessioni invalidate.
    """
    token = extract_token_from_request(request)
    if AUTH_ENABLED:
        result = validate_session(token)
        if not result:
            raise HTTPException(status_code=401, detail="Non autenticato")

    count = destroy_all_sessions()

    # Cancella anche il cookie della sessione corrente
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, path="/", secure=SESSION_COOKIE_SECURE, httponly=True, samesite="strict"
    )
    audit_event(request, "auth_logout_all", sessions_destroyed=count)
    return {"ok": True, "sessions_destroyed": count}


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
    result = validate_session(token)
    if not result:
        raise HTTPException(status_code=401, detail="Non autenticato")

    username, role = result

    # CSRF bootstrap: include the CSRF token so the frontend can restore it
    # after a page reload without requiring a new login.
    csrf_token = get_csrf_token_for_session(token)
    if csrf_token:
        response.headers["X-CSRF-Token"] = csrf_token

    return {
        "authenticated": True,
        "username": username,
        "role": role,
        "auth_enabled": True,
        "default_password": auth_uses_default_password(),
    }
