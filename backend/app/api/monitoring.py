"""
Health check and monitoring endpoints.
"""
import time
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["monitoring"])

# Application start time
START_TIME = time.time()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    uptime_seconds: float
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response model."""
    ready: bool
    checks: Dict[str, Dict[str, Any]]


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.
    Returns 200 OK if the service is running.
    """
    uptime = time.time() - START_TIME

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=round(uptime, 2),
        version="1.0.0",
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(response: Response) -> ReadinessResponse:
    """
    Readiness check endpoint.
    Verifies that all dependencies are available.
    """
    checks = {}
    all_ready = True

    # Check filesystem access
    try:
        from pathlib import Path
        import tempfile

        temp_dir = Path(tempfile.gettempdir())
        test_file = temp_dir / ".health_check"
        test_file.write_text("test")
        test_file.unlink()

        checks["filesystem"] = {"status": "ok", "writable": True}
    except Exception as e:
        checks["filesystem"] = {"status": "error", "error": str(e)}
        all_ready = False

    # Check parser availability
    try:
        from app.parsers.factory import ParserFactory

        ParserFactory()
        checks["parsers"] = {
            "status": "ok",
            "available": True,
        }
    except Exception as e:
        checks["parsers"] = {"status": "error", "error": str(e)}
        all_ready = False

    # Check OCR availability (optional)
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        checks["ocr"] = {"status": "ok", "available": True}
    except Exception:
        checks["ocr"] = {"status": "warning", "available": False, "message": "Tesseract not available"}
        # OCR is optional, so don't mark as not ready

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        ready=all_ready,
        checks=checks,
    )


@router.get("/metrics")
async def metrics() -> Dict[str, Any]:
    """
    Basic metrics endpoint (Prometheus-compatible format can be added later).
    Returns application metrics in JSON format.
    """
    uptime = time.time() - START_TIME

    # Get detector cache stats
    cache_stats = {}
    try:
        from app.detectors.cache import get_detector_cache
        cache = get_detector_cache()
        cache_stats = cache.get_stats()
    except Exception as e:
        logger.warning("Failed to get cache stats: %s", e)
        cache_stats = {"error": str(e)}

    # Get parallel processing config
    try:
        from app.core.config import PARALLEL_FILE_PROCESSING, MAX_PARALLEL_FILES
        parallel_config = {
            "enabled": PARALLEL_FILE_PROCESSING,
            "max_workers": MAX_PARALLEL_FILES,
        }
    except Exception as e:
        logger.warning("Failed to get parallel config: %s", e)
        parallel_config = {"error": str(e)}

    return {
        "app_uptime_seconds": round(uptime, 2),
        "app_version": "1.0.0",
        "app_name": "pseudonymization-tool",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detector_cache": cache_stats,
        "parallel_processing": parallel_config,
    }
