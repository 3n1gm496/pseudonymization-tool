"""
Punto di ingresso dell'applicazione Local Pseudonymization Tool.
Il server è configurato per ascoltare SOLO su 127.0.0.1 (localhost).
"""
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.core.config import SERVER_HOST, SERVER_PORT, TEMP_BASE_DIR
from app.core.batch_manager import start_cleanup_scheduler

# Configurazione logging: nessun valore sensibile nei log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ─── Lifespan (startup/shutdown moderno, compatibile FastAPI >= 0.93) ─────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=" * 60)
    logger.info("Local Pseudonymization Tool — vNext v2.0.0")
    logger.info("Server in ascolto su: http://%s:%s", SERVER_HOST, SERVER_PORT)
    logger.info("SICUREZZA: Nessuna chiamata di rete esterna verra' effettuata.")
    logger.info("=" * 60)
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
    yield
    # Shutdown
    logger.info("Server in arresto.")


# ─── Applicazione FastAPI ─────────────────────────────────────────────────────

app = FastAPI(
    title="Local Pseudonymization Tool",
    description="Tool locale per la pseudonimizzazione di documenti sensibili. Solo uso locale.",
    version="2.0.0-vNext",
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
