"""
Punto di ingresso dell'applicazione Local Pseudonymization Tool.
Il server è configurato per ascoltare SOLO su 127.0.0.1 (localhost).
"""

import base64
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from app import __version__
from app.api.audit_routes import router as audit_router
from app.api.auth_routes import router as auth_router
from app.api.batches_routes import router as batches_router
from app.api.console_routes import router as console_router
from app.api.revert_routes import router as revert_router
from app.api.routes import router as api_router
from app.api.settings_routes import router as settings_router
from app.api.users_routes import router as users_router
from app.core.auth import (
    SESSION_COOKIE_NAME,
    auth_uses_default_password,
    extract_token_from_request,
    validate_csrf_token,
    validate_session,
)
from app.core.batch_manager import start_cleanup_scheduler
from app.core.config import SERVER_HOST, SERVER_PORT, TEMP_BASE_DIR, validate_writable_paths
from app.core.profiles import get_config, print_profile_info, validate_production_secrets
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Get deployment profile configuration
_profile_config = get_config()

# Configure logging based on deployment profile
log_level = getattr(logging, _profile_config.log_level.upper(), logging.INFO)
log_format = (
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    if not _profile_config.json_logs
    else "%(message)s"  # JSON logging handled by structured logging library
)

logging.basicConfig(
    level=log_level,
    format=log_format,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ─── Lifespan (startup/shutdown moderno, compatibile FastAPI >= 0.93) ─────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print_profile_info()
    logger.info("Local Pseudonymization Tool — v%s", __version__)
    logger.info("Server in ascolto su: http://%s:%s", SERVER_HOST, SERVER_PORT)
    logger.info("SICUREZZA: Nessuna chiamata di rete esterna verra' effettuata.")

    # Validate writable paths early
    validate_writable_paths()

    TEMP_BASE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from app.core.policies import save_default_policies

        save_default_policies()
    except Exception as e:
        logger.warning("Impossibile salvare le policy di default: %s", e)
    try:
        from app.detectors.dictionary_detector import get_dictionary_detector

        detector = get_dictionary_detector()
        logger.info("DictionaryDetector: %d termini caricati.", detector.loaded_terms_count)
    except Exception as e:
        logger.warning("Errore nel caricamento dei dizionari: %s", e)
    start_cleanup_scheduler()
    logger.info("Cleanup scheduler avviato.")
    # Inizializza il database utenti e bootstrap admin
    try:
        from app.core.user_manager import initialize as init_users

        init_users()
        logger.info("User manager inizializzato.")
    except Exception as e:
        logger.warning("Errore nell'inizializzazione del user manager: %s", e)
    # Validazione secrets obbligatori (PROD/STAGING)
    secret_errors = validate_production_secrets()
    if secret_errors:
        for err in secret_errors:
            logger.error("❌ Configurazione mancante: %s", err)
        raise RuntimeError(
            f"Avvio bloccato: {len(secret_errors)} secret/i obbligatori non configurati. "
            "Controlla i log per i dettagli."
        )

    if _profile_config.auth_enabled:
        logger.info("Autenticazione API: ATTIVA")
        if auth_uses_default_password():
            logger.warning("⚠️  AUTH_PASSWORD non impostata (nessun default disponibile).")
    else:
        logger.warning("Autenticazione API: DISATTIVATA")
    yield
    # ─── Graceful Shutdown ───────────────────────────────────────────────────
    logger.info("Server in arresto — avvio graceful shutdown...")
    # 1. Fermare il cleanup scheduler (evita task in background durante lo shutdown)
    try:
        from app.core.batch_manager import stop_cleanup_scheduler

        stop_cleanup_scheduler()
        logger.info("Cleanup scheduler fermato.")
    except Exception as e:
        logger.warning("Errore nel fermare il cleanup scheduler: %s", e)
    # 2. Log finale
    logger.info("Graceful shutdown completato.")


# ─── Applicazione FastAPI ─────────────────────────────────────────────────────

# Determine docs_url based on profile (disable in production)
docs_url = "/api/docs" if _profile_config.swagger_ui_enabled else None

app = FastAPI(
    title="Local Pseudonymization Tool",
    description="Tool locale per la pseudonimizzazione di documenti sensibili. Solo uso locale.",
    version=__version__,
    docs_url=docs_url,
    redoc_url=None,
    lifespan=lifespan,
)

# CORS: configured per deployment profile
app.add_middleware(
    CORSMiddleware,
    allow_origins=_profile_config.cors_origins,
    allow_credentials=_profile_config.cors_allow_credentials,
    allow_methods=_profile_config.cors_allow_methods,
    allow_headers=_profile_config.cors_allow_headers,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """
    Aggiunge security headers HTTP a tutte le risposte.

    Headers applicati:
    - X-Content-Type-Options: impedisce MIME-type sniffing
    - X-Frame-Options: impedisce clickjacking (embedding in iframe)
    - X-XSS-Protection: abilita filtro XSS nei browser legacy
    - Referrer-Policy: limita le informazioni nel Referer header
    - Permissions-Policy: disabilita API browser non necessarie
    - Strict-Transport-Security: forza HTTPS (solo in PROD/STAGING)
    - Content-Security-Policy: limita le sorgenti di contenuto
    """
    response = await call_next(request)

    # Headers universali (tutti i profili)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

    # HSTS: solo in PROD e STAGING (richiede HTTPS)
    if _profile_config.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # CSP: policy restrittiva per SPA locale
    # 'self' per script/style/img; no eval, no inline script
    # Swagger UI richiede 'unsafe-inline' per i suoi stili
    if _profile_config.swagger_ui_enabled:
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
    else:
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
    response.headers["Content-Security-Policy"] = csp

    return response


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Skip auth check if disabled in profile
    if not _profile_config.auth_enabled:
        return await call_next(request)

    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)

    public_paths = {
        "/api/health",
        "/api/ready",
        "/api/metrics",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/ldap-status",
        "/api/docs",
    }

    if path.startswith("/api") and path not in public_paths and not path.startswith("/api/docs"):
        token = extract_token_from_request(request)
        session_result = validate_session(token)
        if not session_result:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})
        username, role = session_result
        request.state.auth_user = username
        request.state.auth_role = role

    return await call_next(request)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """
    Propagate or generate X-Request-ID for distributed tracing.

    Reads the X-Request-ID header sent by the client (e.g. a load balancer or
    the frontend). If absent, generates a new UUID. The ID is stored on
    request.state.correlation_id so route handlers and Celery task enqueue
    can attach it to async tasks. The ID is also echoed in the response header
    so the client can correlate responses with its own request logs.
    """
    correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """
    Valida CSRF token per tutti i metodi mutanti (POST/PUT/DELETE/PATCH).

    Questo middleware protegge contro attacchi CSRF validando il token per tutte
    le richieste che modificano lo stato del server.

    NOTA: Registrato PRIMA di auth_middleware nel codice per essere eseguito DOPO
    (middleware FastAPI sono LIFO: ultimo registrato = primo eseguito).
    """
    # Skip per metodi sicuri (idempotenti)
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return await call_next(request)

    path = request.url.path

    # Path esclusi dalla validazione CSRF
    csrf_exempt_paths = {
        "/api/auth/login",  # Login non ha ancora token CSRF
        "/api/health",  # Endpoint di monitoring
        "/api/ready",  # Endpoint di monitoring
        "/api/metrics",  # Prometheus metrics (GET only, ma esentato per coerenza)
        "/api/docs",  # Documentazione API
        "/api/auth/me",  # Auth status check
    }

    if path in csrf_exempt_paths or path.startswith("/api/docs"):
        return await call_next(request)

    # Skip se auth disabilitato (dev/test mode)
    if not _profile_config.auth_enabled:
        return await call_next(request)

    # Skip CSRF per path pubblici (stessa logica di auth_middleware)
    # Se il path non richiede auth, non richiede CSRF
    public_paths = {
        "/api/health",
        "/api/ready",
        "/api/metrics",
        "/api/auth/login",
        "/api/auth/me",
        "/api/docs",
    }

    if path in public_paths or not path.startswith("/api"):
        return await call_next(request)

    # Prima verifica se c'è una sessione attiva
    # Se non c'è session cookie, delega ad auth_middleware (che darà 401)
    # Questo garantisce l'ordine corretto: 401 (no auth) prima di 403 (CSRF)
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_cookie or "." not in session_cookie:
        # No session cookie → richiesta non autenticata
        # Skip CSRF validation, let auth_middleware handle it (will return 401)
        return await call_next(request)

    # A questo punto abbiamo un session cookie, validiamo CSRF
    csrf_token = request.headers.get("X-CSRF-Token") or request.query_params.get("csrf_token")

    # Extract session_id dal cookie (formato: base64_payload.signature)
    # NOTA: Il payload è base64 URL-safe con padding strippato, come in auth.py
    try:
        payload_b64 = session_cookie.split(".", 1)[0]
        # Add padding for base64 urlsafe decoding (same as auth.py _b64_decode)
        padding = "=" * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode((payload_b64 + padding).encode("utf-8")).decode("utf-8")
        session_id = payload.split(":", 1)[0]
    except Exception as e:
        logger.warning("CSRF validation failed: could not extract session_id: %s", e)
        return JSONResponse(status_code=403, content={"detail": "CSRF validation failed: invalid session"})

    # Valida token CSRF usando la funzione esistente
    if not validate_csrf_token(session_id, csrf_token):
        logger.warning(
            "CSRF validation failed: invalid or missing token (path=%s, session_id=%s...)",
            path,
            session_id[:8] if session_id else "unknown",
        )
        return JSONResponse(status_code=403, content={"detail": "CSRF token invalid or missing"})

    # CSRF validated successfully, proceed with request
    return await call_next(request)


# ─── Global exception handler ────────────────────────────────────────────────
# Catches any unhandled exception that escapes route handlers.
# Logs the full traceback internally; returns a generic 500 to the client
# so that internal error details (stack traces, file paths, library names)
# are never exposed in API responses.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Fallback handler for unhandled exceptions.

    Security rationale: returning str(exc) in HTTP responses leaks internal
    implementation details (file paths, library versions, SQL queries, etc.).
    This handler ensures a generic message is always sent to the client while
    the full traceback is preserved in server logs for debugging.
    """
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Errore interno del server. Contatta l'amministratore."},
    )


# Registra i router API
app.include_router(auth_router)
app.include_router(console_router)
app.include_router(revert_router)
app.include_router(batches_router)
app.include_router(settings_router)
app.include_router(audit_router)
app.include_router(users_router)
app.include_router(api_router)

# Serve i file statici del frontend React (production build o fallback)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_BUILD = BASE_DIR / "frontend" / "dist"
FRONTEND_DEV = BASE_DIR / "frontend"

# Determina da quale directory servire
if FRONTEND_BUILD.exists():
    frontend_dir = FRONTEND_BUILD
    logger.info("Serving React production build from: %s", frontend_dir)
elif FRONTEND_DEV.exists():
    frontend_dir = FRONTEND_DEV
    logger.info("Serving fallback frontend from: %s", frontend_dir)
else:
    frontend_dir = None
    logger.warning("Frontend directory not found")

if frontend_dir and frontend_dir.exists():
    # Mount static files if exists
    if (frontend_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    # SPA routing: serve index.html for unknown routes (client-side routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA with client-side routing fallback."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        requested_path = frontend_dir / full_path
        if requested_path.exists() and requested_path.is_file():
            return FileResponse(str(requested_path))

        index_path = frontend_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))

        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/")
    async def serve_root():
        """Serve the main application."""
        index_path = frontend_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Frontend not configured yet")

else:

    @app.get("/")
    async def serve_placeholder():
        return {"message": "Frontend not found. Ensure frontend/ directory exists."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="info",
    )
