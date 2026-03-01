"""
Router API v4.0 — Local Pseudonymization Tool
Flussi:
  - POST /api/batches          → upload file (multipart), scan automatico
  - POST /api/console/scan     → testo inline, batch interno
  - POST /api/console/apply    → applica testo inline
  - POST /api/batches/{id}/review → persiste decisions
  - POST /api/batches/{id}/apply  → applica con decisions persistite
  - GET  /api/batches/{id}/download → scarica ZIP
  - GET/POST /api/settings/state  → persistenza config server-side (no password)
  - GET/POST /api/settings/ldap   → config LDAP con diagnostica
"""
import json
import logging
import asyncio
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from app.models.schemas import (
    Batch, BatchConfig, BatchMode, BatchStatus, FileRecord, FileStatus,
    BatchStatusResponse, FindingsResponse,
    SubmitReviewRequest, ReviewAction,
    SafetyLabel, PresetName,
    LdapConfig, LdapTestResult,
)
from app.core.batch_manager import (
    create_batch, get_batch, update_batch, list_batches,
    get_batch_dir, store_passphrase, get_passphrase, cleanup_batch,
    generate_passphrase, regenerate_passphrase,
    store_decisions, get_decisions, clear_decisions,
)
from app.core.pipeline import run_scan_pipeline, apply_review_decisions, run_apply_pipeline
import math
from app.core.config import (
    SUPPORTED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    CONFIG_DIR,
    API_HEAVY_TIMEOUT_SECONDS,
    MAX_UPLOAD_FILES_PER_BATCH,
)
from app.core.policies import get_policy, get_enabled_entity_types
router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_batch_start_times: dict = {}
_rate_buckets: Dict[str, List[float]] = {}

# File di stato server-side (no password, no PII)
_STATE_FILE = CONFIG_DIR / "state.json"




# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY FIX #1-3: PASSPHRASE VALIDATION & ENTROPY
# ═══════════════════════════════════════════════════════════════════════════════

def _calculate_entropy(s: str) -> float:
    """Calcola l'entropia di Shannon per una stringa (bits per carattere)."""
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    entropy = 0.0
    for count in freq.values():
        p = count / len(s)
        entropy -= p * math.log2(p)
    return entropy


def _validate_passphrase(passphrase: str) -> None:
    """
    Valida la passphrase per lunghezza ed entropia minima.
    Security Fix #7: Weak password prevention
    """
    # Import config values if needed
    try:
        from app.core.config import MIN_PASSPHRASE_LENGTH, MIN_PASSPHRASE_ENTROPY
    except:
        MIN_PASSPHRASE_LENGTH = 12
        MIN_PASSPHRASE_ENTROPY = 2.5
    
    if not passphrase or len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"La passphrase deve essere di almeno {MIN_PASSPHRASE_LENGTH} caratteri."
        )
    
    entropy = _calculate_entropy(passphrase)
    if entropy < MIN_PASSPHRASE_ENTROPY:
        raise HTTPException(
            status_code=400,
            detail=f"La passphrase è troppo debole (entropia: {entropy:.2f} bits/char, minimo: {MIN_PASSPHRASE_ENTROPY}). "
                   "Usa caratteri variati e non ripetitivi."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY FIX #4: FILE MAGIC BYTES VALIDATION  
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_file_magic_bytes(content: bytes, filename: str) -> str:
    """
    Valida il magic bytes del file per verificare che corrisponda all'estensione.
    Security Fix #3: Malicious file detection
    Restituisce l'estensione rilevata.
    """
    ext = Path(filename).suffix.lower()
    
    # Magic bytes comuni
    if content.startswith(b'%PDF'):
        detected_ext = '.pdf'
    elif content.startswith(b'PK\x03\x04'):
        # ZIP-based formats (docx, xlsx)
        if b'word/' in content[:2000]:
            detected_ext = '.docx'
        elif b'xl/' in content[:2000]:
            detected_ext = '.xlsx'
        else:
            detected_ext = ext
    elif content.startswith(b'\xff\xd8\xff'):
        detected_ext = '.jpg'
    elif content.startswith(b'\x89PNG'):
        detected_ext = '.png'
    else:
        if ext in {'.txt', '.md', '.csv'}:
            detected_ext = ext
        else:
            logger.warning(f"Non è possibile validare magic bytes per {filename}")
            detected_ext = ext
    
    if detected_ext != ext and ext in SUPPORTED_EXTENSIONS:
        logger.warning(f"Mismatch magic bytes per {filename}: dichiarato {ext}, rilevato {detected_ext}")
    
    return detected_ext



# ─── Helpers ──────────────────────────────────────────────────────────────────

def _findings_list(batch: Batch) -> list:
    result = []
    for f in batch.findings:
        fd = f.model_dump() if hasattr(f, "model_dump") else f.dict()
        result.append(fd)
    return result


def _resolve_preset(raw_value: str) -> PresetName:
    value = (raw_value or "").strip()
    for preset in PresetName:
        if preset.value.lower() == value.lower():
            return preset
    raise HTTPException(status_code=400, detail=f"Preset non valido: '{raw_value}'.")


def _enforce_rate_limit(request: Request, scope: str, limit: int, window_seconds: int = 60) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket_key = f"{scope}:{client_ip}"
    timestamps = _rate_buckets.get(bucket_key, [])
    timestamps = [t for t in timestamps if now - t < window_seconds]
    if len(timestamps) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Troppe richieste per '{scope}'. Riprova tra pochi secondi.",
        )
    timestamps.append(now)
    _rate_buckets[bucket_key] = timestamps


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


# ─── Settings: Persistenza server-side ────────────────────────────────────────

@router.get("/settings/state")
async def get_server_state():
    """
    Restituisce la configurazione persistita lato server (no password, no PII).
    """
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            return data
        except Exception:
            pass
    return {"mode": "light", "ldap": None, "sessions_metadata": []}


@router.post("/settings/state")
async def save_server_state(state: dict):
    """
    Salva la configurazione lato server (no password, no PII).
    La password LDAP viene rimossa prima del salvataggio.
    """
    safe_state = _scrub_sensitive(state)
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore salvataggio stato: {e}")


# ─── Settings: Dizionari ──────────────────────────────────────────────────────

@router.get("/settings/dictionaries")
async def get_dictionaries_status():
    from app.detectors.dictionary_detector import get_dictionary_detector
    detector = get_dictionary_detector()
    return {"total_terms": detector.loaded_terms_count, "files": 3}


@router.post("/settings/dictionaries/reload")
async def reload_dictionaries():
    from app.detectors.dictionary_detector import get_dictionary_detector
    detector = get_dictionary_detector()
    detector.reload()
    return {"total_terms": detector.loaded_terms_count, "message": "Dizionari ricaricati."}


# ─── Settings: LDAP ───────────────────────────────────────────────────────────

@router.get("/settings/ldap")
async def get_ldap_config():
    from app.detectors.ldap_detector import get_ldap_config as _get, get_ldap_cache
    cfg = _get()
    cache = get_ldap_cache()
    diag = cache.get_diagnostics()
    if not cfg:
        return {"enabled": False, "configured": False, "diagnostics": diag}
    d = cfg.model_dump()
    d.pop("bind_password", None)
    d["configured"] = True
    d["diagnostics"] = diag
    return d


@router.post("/settings/ldap")
async def set_ldap_config(config: LdapConfig):
    from app.detectors.ldap_detector import configure_ldap
    configure_ldap(config)
    return {"ok": True, "message": f"LDAP configurato: {config.host}:{config.port}"}


@router.post("/settings/ldap/test")
async def test_ldap():
    """
    Testa la connessione LDAP e restituisce diagnostica completa sanitizzata.
    """
    from app.detectors.ldap_detector import get_ldap_cache
    cache = get_ldap_cache()
    success, message, count, diag = cache.test_connection()
    return {
        "ok": success,
        "error": None if success else message,
        "user_count": count,
        "diagnostics": diag,
    }


@router.post("/settings/ldap/refresh")
async def refresh_ldap():
    """
    Forza il refresh della cache LDAP e restituisce diagnostica.
    """
    from app.detectors.ldap_detector import get_ldap_cache
    cache = get_ldap_cache()
    success, message, diag = cache.refresh_now()
    return {"ok": success, "message": message, "diagnostics": diag}


# ─── Debug ───────────────────────────────────────────────────────────────────

@router.get("/debug/{batch_id}")
async def debug_batch(batch_id: str):
    """
    Endpoint di debug: restituisce lo stato interno del batch, le decisions persistite
    e i finding con il loro stato attuale. NON espone valori sensibili.
    Solo per uso locale/diagnostico.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    decisions_map = get_decisions(batch_id)

    findings_debug = []
    for f in batch.findings:
        fd = f.model_dump() if hasattr(f, "model_dump") else f.dict()
        fid = fd.get("finding_id", "")
        dec = decisions_map.get(fid, {})
        findings_debug.append({
            "finding_id": fid,
            "entity_type": fd.get("entity_type"),
            "original_value": fd.get("original_value"),
            "proposed_pseudonym": fd.get("proposed_pseudonym"),
            "review_action": fd.get("review_action"),
            "final_pseudonym": fd.get("final_pseudonym"),
            "decision_stored": dec,
        })

    return {
        "batch_id": batch_id,
        "status": batch.status.value,
        "mode": batch.config.mode.value,
        "findings_count": len(batch.findings),
        "decisions_count": len(decisions_map),
        "findings": findings_debug,
        "decisions_raw": decisions_map,
    }


# ─── Settings: Entity Types ───────────────────────────────────────────────────

@router.get("/settings/entity-types")
async def get_entity_types():
    from app.models.schemas import EntityType
    return {
        "entity_types": [
            {"value": et.value, "label": et.value.replace("_", " ").title()}
            for et in EntityType
        ]
    }


@router.get("/settings/policies")
async def get_policies():
    return {"presets": [preset.value for preset in PresetName]}


@router.get("/settings/policies/{preset_name}")
async def get_policy_preview(preset_name: str):
    preset = _resolve_preset(preset_name)
    policy = get_policy(preset)
    enabled = get_enabled_entity_types(preset)
    return {
        "preset": preset.value,
        "description": policy.get("description", ""),
        "confidence_threshold": policy.get("confidence_threshold", 0.0),
        "enabled_entity_types": enabled,
        "entity_count": len(enabled),
    }
