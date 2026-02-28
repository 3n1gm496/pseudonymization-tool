"""
Punto di ingresso dell'applicazione Local Pseudonymization Tool.
Il server è configurato per ascoltare SOLO su 127.0.0.1 (localhost).
"""
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.api.monitoring import router as monitoring_router
from app.core.config import SERVER_HOST, SERVER_PORT
from app.core.logging_config import configure_logging, get_logger, log_request_start, log_request_end

# Configure structured logging
configure_logging(log_level="INFO", json_logs=False)
logger = get_logger(__name__)


# ─── Lifespan (startup/shutdown moderno, compatibile FastAPI >= 0.93) ─────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=" * 60)
    logger.info("Local Pseudonymization Tool — MVP v1.0.0")
    logger.info("Server in ascolto su: http://%s:%s", SERVER_HOST, SERVER_PORT)
    logger.info("SICUREZZA: Nessuna chiamata di rete esterna verra' effettuata.")
    logger.info("=" * 60)
    yield
    # Shutdown
    logger.info("Server in arresto.")


# ─── Applicazione FastAPI ─────────────────────────────────────────────────────

app = FastAPI(
    title="Local Pseudonymization Tool",
    description="Tool locale per la pseudonimizzazione di documenti sensibili. Solo uso locale.",
    version="1.0.0-MVP",
    docs_url="/api/docs",  # Swagger UI disponibile solo in locale
    redoc_url=None,
    lifespan=lifespan,
)

# CORS: solo localhost (per sicurezza)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://127.0.0.1:{SERVER_PORT}",
        f"http://localhost:{SERVER_PORT}",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Registra i router API
app.include_router(router)
app.include_router(monitoring_router, prefix="/api")


# Request logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all requests with timing and correlation ID."""
    request_id = str(uuid.uuid4())
    start_time = time.time()

    # Add request ID to state
    request.state.request_id = request_id

    log_request_start(
        method=request.method,
        path=request.url.path,
        request_id=request_id,
    )

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000

    log_request_end(
        method=request.method,
        path=request.url.path,
        request_id=request_id,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    # Add correlation ID to response headers
    response.headers["X-Request-ID"] = request_id

    return response

# Serve i file statici del frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", response_class=FileResponse)
    async def serve_frontend():
        """Serve l'interfaccia web principale."""
        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:
    logger.warning("Directory frontend non trovata: %s", FRONTEND_DIR)

    @app.get("/")
    async def serve_placeholder():
        return {"message": "Frontend non trovato. Avviare il server dalla directory corretta."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="info",
    )
