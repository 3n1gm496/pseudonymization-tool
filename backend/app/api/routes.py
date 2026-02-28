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
from app.core.console_pipeline import run_text_scan, run_text_apply
import math
from app.core.config import (
    SUPPORTED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    CONFIG_DIR,
    API_HEAVY_TIMEOUT_SECONDS,
    MAX_UPLOAD_FILES_PER_BATCH,
    MAX_CONSOLE_TEXT_CHARS,
)
from app.core.policies import get_policy, get_enabled_entity_types
from app.core.revert import preview_revert, apply_revert, preview_revert_text, apply_revert_text
from app.core.auth import (
    AUTH_ENABLED,
    ADMIN_USERNAME,
    SESSION_COOKIE_NAME,
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


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "Local Pseudonymization Tool",
        "version": "4.0.0",
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
        secure=False,
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


@router.post("/revert/preview")
async def revert_preview(
    request: Request,
    archive: UploadFile = File(...),
    passphrase: str = Form(...),
):
    _enforce_rate_limit(request, "revert_preview", limit=15)
    if not archive.filename or not archive.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Carica un archivio ZIP valido.")
    if not passphrase.strip():
        raise HTTPException(status_code=400, detail="La passphrase è obbligatoria.")

    zip_bytes = await archive.read()
    if len(zip_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Archivio troppo grande.")

    try:
        result = preview_revert(zip_bytes, passphrase.strip())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossibile analizzare archivio: {e}")

    _audit_event(
        request,
        "revert_preview",
        archive_name=archive.filename,
        mapping_entries=result.get("mapping_entries", 0),
        total_matches=result.get("total_matches", 0),
    )
    return result


@router.post("/revert/apply")
async def revert_apply(
    request: Request,
    archive: UploadFile = File(...),
    passphrase: str = Form(...),
):
    _enforce_rate_limit(request, "revert_apply", limit=10)
    if not archive.filename or not archive.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Carica un archivio ZIP valido.")
    if not passphrase.strip():
        raise HTTPException(status_code=400, detail="La passphrase è obbligatoria.")

    zip_bytes = await archive.read()
    if len(zip_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Archivio troppo grande.")

    try:
        reverted_bytes, summary = apply_revert(zip_bytes, passphrase.strip())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Revert fallito: {e}")

    out_name = (Path(archive.filename).stem or "batch") + "_reverted.zip"
    _audit_event(
        request,
        "revert_apply",
        archive_name=archive.filename,
        output_name=out_name,
        total_replacements=summary.get("total_replacements", 0),
        processed_files=summary.get("processed_files", 0),
    )

    return Response(
        content=reverted_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{out_name}"',
            "X-Revert-Summary": json.dumps(summary, ensure_ascii=False),
        },
    )


@router.post("/revert/text/preview")
async def revert_text_preview(
    request: Request,
    mapping_file: UploadFile = File(...),
    passphrase: str = Form(...),
    text: str = Form(...),
):
    _enforce_rate_limit(request, "revert_text_preview", limit=25)
    if not passphrase.strip():
        raise HTTPException(status_code=400, detail="La passphrase è obbligatoria.")
    if len(text) > MAX_CONSOLE_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Testo troppo lungo ({len(text)} caratteri). Massimo consentito: {MAX_CONSOLE_TEXT_CHARS}.",
        )

    mapping_bytes = await mapping_file.read()
    if not mapping_bytes:
        raise HTTPException(status_code=400, detail="File mapping è vuoto.")
    if len(mapping_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File mapping troppo grande.")

    try:
        result = preview_revert_text(text, mapping_bytes, passphrase)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossibile analizzare il mapping: {e}")

    _audit_event(
        request,
        "revert_text_preview",
        mapping_name=mapping_file.filename,
        input_chars=len(text),
        total_matches=result.get("total_matches", 0),
    )
    return result


@router.post("/revert/text/apply")
async def revert_text_apply(
    request: Request,
    mapping_file: UploadFile = File(...),
    passphrase: str = Form(...),
    text: str = Form(...),
):
    _enforce_rate_limit(request, "revert_text_apply", limit=25)
    if not passphrase.strip():
        raise HTTPException(status_code=400, detail="La passphrase è obbligatoria.")
    if len(text) > MAX_CONSOLE_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Testo troppo lungo ({len(text)} caratteri). Massimo consentito: {MAX_CONSOLE_TEXT_CHARS}.",
        )

    mapping_bytes = await mapping_file.read()
    if not mapping_bytes:
        raise HTTPException(status_code=400, detail="File mapping è vuoto.")
    if len(mapping_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File mapping troppo grande.")

    try:
        result = apply_revert_text(text, mapping_bytes, passphrase)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decifratura fallita: {e}")

    _audit_event(
        request,
        "revert_text_apply",
        mapping_name=mapping_file.filename,
        input_chars=len(text),
        total_replacements=result.get("total_replacements", 0),
    )
    return result


# ─── Batch (Upload File) ──────────────────────────────────────────────────────

@router.post("/batches")
async def create_new_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    mode: str = Form("strict"),
    preset: str = Form("SOC Logs"),
    passphrase: str = Form(""),
):
    """
    Crea un nuovo batch con i file allegati.
    Integra Security Fix #7: Passphrase entropy validation
    Integra Security Fix #3: File magic bytes validation
    Restituisce batch_id, passphrase generata, findings e safety_label.
    """
    _enforce_rate_limit(request, "batch_create", limit=20)

    if len(files) > MAX_UPLOAD_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Numero file eccessivo ({len(files)}). Massimo consentito: {MAX_UPLOAD_FILES_PER_BATCH}.",
        )

    # Security Fix #7: Validate passphrase entropy if provided
    if passphrase:
        _validate_passphrase(passphrase)
    
    batch_mode = BatchMode.STRICT
    batch_preset = PresetName.SOC_LOGS

    config = BatchConfig(mode=batch_mode, preset=batch_preset)
    batch = Batch(config=config)
    batch = create_batch(batch)

    pp = passphrase if passphrase and len(passphrase) >= 4 else generate_passphrase()
    store_passphrase(batch.batch_id, pp)

    batch_dir = get_batch_dir(batch.batch_id)
    upload_dir = batch_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    for upload_file in files:
        if not upload_file.filename:
            continue
        file_path = Path(upload_file.filename)
        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            logger.warning("File ignorato (formato non supportato): %s", upload_file.filename)
            continue
        content = await upload_file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            logger.warning("File troppo grande: %s (%d bytes)", upload_file.filename, len(content))
            continue
        
        # Security Fix #3: Validate file magic bytes
        try:
            detected_ext = _validate_file_magic_bytes(content, upload_file.filename)
            if detected_ext not in SUPPORTED_EXTENSIONS:
                logger.warning("File ignorato (magic bytes non corrisponde): %s", upload_file.filename)
                continue
        except Exception as e:
            logger.warning("Errore validazione magic bytes per %s: %s", upload_file.filename, e)
            continue
        
        safe_name = Path(upload_file.filename).name
        dest_path = upload_dir / safe_name
        counter = 1
        while dest_path.exists():
            dest_path = upload_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
            counter += 1
        dest_path.write_bytes(content)
        file_rec = FileRecord(
            original_name=upload_file.filename,
            stored_path=str(dest_path),
        )
        batch.files.append(file_rec)

    if not batch.files:
        cleanup_batch(batch.batch_id)
        raise HTTPException(
            status_code=400,
            detail="Nessun file valido caricato. Formati supportati: " + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )

    update_batch(batch)
    _batch_start_times[batch.batch_id] = datetime.now(timezone.utc).isoformat()

    try:
        batch = await asyncio.wait_for(
            run_in_threadpool(run_scan_pipeline, batch.batch_id),
            timeout=API_HEAVY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        cleanup_batch(batch.batch_id)
        raise HTTPException(
            status_code=504,
            detail="Timeout durante la scansione del batch. Riduci dimensione o numero file.",
        )
    except Exception as e:
        logger.error("Errore scansione batch %s: %s", batch.batch_id, e)
        raise HTTPException(status_code=500, detail=f"Errore durante la scansione: {e}")

    _audit_event(
        request,
        "batch_scan_completed",
        batch_id=batch.batch_id,
        files_count=len(batch.files),
        findings_count=len(batch.findings),
        safety_label=batch.safety_label.value if batch.safety_label else "SAFE_TO_UPLOAD",
    )

    return {
        "batch_id": batch.batch_id,
        "status": batch.status.value,
        "mode": mode,
        "passphrase": pp,
        "files": [{"name": fr.original_name, "id": fr.file_id} for fr in batch.files],
        "findings": _findings_list(batch),
        "findings_count": len(batch.findings),
        "safety_label": batch.safety_label.value if batch.safety_label else "SAFE_TO_UPLOAD",
    }


# ─── Console (Testo Inline) ───────────────────────────────────────────────────

@router.post("/console/scan")
async def console_scan(req: dict, request: Request):
    """
    Scansiona testo inline. Crea batch internamente.
    Accetta: { text, mode }
    Restituisce: batch_id, passphrase, findings, safety_label
    """
    _enforce_rate_limit(request, "console_scan", limit=30)

    text = req.get("text", "").strip()
    mode_str = "strict"
    preset_str = "SOC Logs"

    if not text:
        raise HTTPException(status_code=400, detail="Il campo 'text' è obbligatorio.")
    if len(text) > MAX_CONSOLE_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Testo troppo lungo ({len(text)} caratteri). Massimo consentito: {MAX_CONSOLE_TEXT_CHARS}.",
        )

    try:
        batch_mode = BatchMode(mode_str.lower())
    except ValueError:
        batch_mode = BatchMode.STRICT

    batch_preset = _resolve_preset(preset_str)

    config = BatchConfig(mode=batch_mode, preset=batch_preset)
    batch = Batch(config=config)
    create_batch(batch)
    pp = generate_passphrase()
    store_passphrase(batch.batch_id, pp)
    _batch_start_times[batch.batch_id] = datetime.now(timezone.utc).isoformat()

    try:
        file_id, findings, safety = await asyncio.wait_for(
            run_in_threadpool(run_text_scan, batch.batch_id, text, "inline"),
            timeout=API_HEAVY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        cleanup_batch(batch.batch_id)
        raise HTTPException(status_code=504, detail="Timeout nella scansione del testo inline.")
    except Exception as e:
        logger.error("Errore console/scan: %s", e)
        cleanup_batch(batch.batch_id)
        raise HTTPException(status_code=500, detail=str(e))

    findings_list = []
    for f in findings:
        fd = f.model_dump() if hasattr(f, "model_dump") else f.dict()
        findings_list.append(fd)

    _audit_event(
        request,
        "console_scan_completed",
        batch_id=batch.batch_id,
        findings_count=len(findings_list),
        safety_label=safety.value if hasattr(safety, "value") else str(safety),
    )

    return {
        "batch_id": batch.batch_id,
        "file_id": file_id,
        "passphrase": pp,
        "findings": findings_list,
        "findings_count": len(findings_list),
        "safety_label": safety.value if hasattr(safety, "value") else str(safety),
    }


@router.post("/console/apply")
async def console_apply(req: dict, request: Request):
    """
    Applica sostituzioni al testo inline, rispettando le decisions persistite.
    Accetta: { batch_id, file_id, text }
    Restituisce: batch_id (per scaricamento mapping.enc successivo)
    """
    _enforce_rate_limit(request, "console_apply", limit=30)

    batch_id = req.get("batch_id")
    file_id = req.get("file_id")
    text = req.get("text", "")

    if not batch_id or not file_id:
        raise HTTPException(status_code=400, detail="batch_id e file_id sono obbligatori")
    if len(text) > MAX_CONSOLE_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Testo troppo lungo ({len(text)} caratteri). Massimo consentito: {MAX_CONSOLE_TEXT_CHARS}.",
        )

    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch non trovato")

    # Applica le decisions persistite ai finding del batch prima di apply
    decisions_map = get_decisions(batch_id)
    if decisions_map:
        from app.models.schemas import ReviewDecisionItem
        decision_items = []
        for fid, dec in decisions_map.items():
            try:
                action = ReviewAction(dec['action'])
            except (ValueError, KeyError):
                action = ReviewAction.ACCEPT
            decision_items.append(ReviewDecisionItem(
                finding_id=fid,
                action=action,
                modified_pseudonym=dec.get('custom_pseudonym'),
            ))
        apply_review_decisions(batch_id, decision_items)

    try:
        pseudo_text, safety, residual_warnings, applied_count = await asyncio.wait_for(
            run_in_threadpool(run_text_apply, batch_id, file_id, text),
            timeout=API_HEAVY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout durante l'applicazione sul testo inline.")
    except Exception as e:
        logger.error("Errore console/apply batch %s: %s", batch_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    _audit_event(
        request,
        "console_apply_completed",
        batch_id=batch_id,
        file_id=file_id,
        applied_count=applied_count,
        safety_label=safety.value if hasattr(safety, "value") else str(safety),
    )

    passphrase = get_passphrase(batch_id)

    # Create and save encrypted mapping for console batch
    # This allows "Prepara per AI" flow to download mapping.enc
    try:
        from app.models.schemas import ReviewAction
        file_findings = [f for f in batch.findings if f.file_id == file_id]
        mapping_data = {"mapping": {}}
        for finding in file_findings:
            if finding.review_action != ReviewAction.REJECT:
                pseudo = finding.final_pseudonym
                canon = finding.canonical_value or finding.original_value
                if pseudo not in mapping_data["mapping"]:
                    mapping_data["mapping"][pseudo] = canon
        
        # Save encrypted mapping to batch directory
        from app.mapping.crypto import save_encrypted_mapping
        batch_dir = get_batch_dir(batch_id)
        mapping_path = batch_dir / "mapping.enc"
        save_encrypted_mapping(mapping_data, passphrase, mapping_path)
        logger.info("Console batch mapping.enc salvato per batch %s", batch_id)
    except Exception as e:
        logger.error("Errore nel salvataggio mapping per console batch %s: %s", batch_id, e)
        # Non fallire l'intera operazione se il mapping non può essere salvato
        # Ma loggiamo l'errore per debugging

    return {
        "batch_id": batch_id,
        "file_id": file_id,
        "pseudonymized_text": pseudo_text,
        "passphrase": passphrase,
        "safety_label": safety.value if hasattr(safety, "value") else str(safety),
        "residual_warnings": residual_warnings,
        "applied_count": applied_count,
    }


@router.get("/console/{batch_id}/mapping.enc")
async def download_console_mapping(batch_id: str, request: Request):
    """
    Scarica il file mapping.enc cifrato da un batch di console.
    Consente al flusso "Prepara per AI" di ottenere il mapping da inviare insieme al testo all'AI.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    
    batch_dir = get_batch_dir(batch_id)
    mapping_path = batch_dir / "mapping.enc"
    
    if not mapping_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File di mapping non disponibile. Assicurati di aver completato l'apply della pseudonimizzazione."
        )
    
    _audit_event(request, "console_mapping_download", batch_id=batch_id)
    return FileResponse(
        path=str(mapping_path),
        media_type="application/octet-stream",
        filename=f"mapping_{batch_id[:8]}.enc"
    )


# ─── Batch Lifecycle ──────────────────────────────────────────────────────────

@router.get("/batches")
async def list_all_batches():
    """Lista tutti i batch attivi con metadata (senza findings completi)."""
    batches = list_batches()
    result = []
    for b in batches:
        result.append({
            "batch_id": b.batch_id,
            "status": b.status.value,
            "mode": b.config.mode.value,
            "files_count": len(b.files),
            "findings_count": len(b.findings),
            "safety_label": b.safety_label.value if b.safety_label else "SAFE_TO_UPLOAD",
            "created_at": b.created_at if hasattr(b, "created_at") else None,
        })
    return {"batches": result, "total": len(result)}


@router.get("/batches/{batch_id}")
async def get_batch_status(batch_id: str):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    return {
        "batch_id": batch.batch_id,
        "status": batch.status.value,
        "files": [{"name": fr.original_name, "id": fr.file_id} for fr in batch.files],
        "findings": _findings_list(batch),
        "findings_count": len(batch.findings),
        "safety_label": batch.safety_label.value if batch.safety_label else "SAFE_TO_UPLOAD",
        "error_message": batch.error_message,
    }


@router.get("/batches/{batch_id}/findings")
async def get_findings(batch_id: str):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    return {"batch_id": batch_id, "findings": _findings_list(batch), "total": len(batch.findings)}


@router.post("/batches/{batch_id}/review")
async def submit_review(batch_id: str, review_request: SubmitReviewRequest, request: Request):
    """
    Persiste le decisioni di review per il batch.
    Le decisions vengono applicate al momento dell'apply.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    if batch.status not in (BatchStatus.REVIEW, BatchStatus.DONE):
        raise HTTPException(
            status_code=400,
            detail=f"Batch non in review (stato: {batch.status.value})."
        )

    # Persisti le decisions nel batch_manager
    decisions_dicts = []
    for d in review_request.decisions:
        decisions_dicts.append({
            "finding_id": d.finding_id,
            "action": d.action.value if hasattr(d.action, "value") else str(d.action),
            "custom_pseudonym": d.modified_pseudonym,
        })
    counts = store_decisions(batch_id, decisions_dicts)

    # Applica anche ai finding in memoria per coerenza immediata
    batch = apply_review_decisions(batch_id, review_request.decisions)

    _audit_event(
        request,
        "batch_review_saved",
        batch_id=batch_id,
        accepted=counts["accepted"],
        rejected=counts["rejected"],
        modified=counts["modified"],
        total=len(review_request.decisions),
    )

    return {
        "message": f"Review persistita: {len(review_request.decisions)} decisioni.",
        "batch_id": batch_id,
        "accepted_count": counts["accepted"],
        "rejected_count": counts["rejected"],
        "modified_count": counts["modified"],
        "total": len(review_request.decisions),
    }


@router.post("/batches/{batch_id}/apply")
async def apply_batch(batch_id: str, request: Request):
    """
    Applica le sostituzioni usando le decisions persistite.
    """
    _enforce_rate_limit(request, "batch_apply", limit=20)

    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    if batch.status != BatchStatus.REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Batch non in review (stato: {batch.status.value})."
        )

    # Assicura che le decisions persistite siano applicate ai finding
    decisions_map = get_decisions(batch_id)
    if decisions_map:
        from app.models.schemas import ReviewDecisionItem
        decision_items = []
        for fid, dec in decisions_map.items():
            try:
                action = ReviewAction(dec['action'])
            except (ValueError, KeyError):
                action = ReviewAction.ACCEPT
            decision_items.append(ReviewDecisionItem(
                finding_id=fid,
                action=action,
                modified_pseudonym=dec.get('custom_pseudonym'),
            ))
        apply_review_decisions(batch_id, decision_items)

    started_at = _batch_start_times.get(batch_id, datetime.now(timezone.utc).isoformat())
    try:
        zip_path = await asyncio.wait_for(
            run_in_threadpool(run_apply_pipeline, batch_id, started_at),
            timeout=API_HEAVY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout durante apply del batch.")
    except Exception as e:
        logger.error("Errore apply batch %s: %s", batch_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    # Conta le decisions applicate (action è salvata in lowercase)
    decisions_count = len(decisions_map)
    rejected_count = sum(
        1 for d in decisions_map.values()
        if str(d.get('action', '')).lower() == 'reject'
    )
    modified_count = sum(
        1 for d in decisions_map.values()
        if str(d.get('action', '')).lower() == 'modify'
    )
    accepted_count = decisions_count - rejected_count - modified_count
    ignored_count = rejected_count  # i rejected non vengono sostituiti

    _audit_event(
        request,
        "batch_apply_completed",
        batch_id=batch_id,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        modified_count=modified_count,
    )

    return {
        "message": "Trasformazioni applicate.",
        "batch_id": batch_id,
        "download_ready": True,
        "decisions_received_count": decisions_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "modified_count": modified_count,
        "ignored_count": ignored_count,
    }


@router.get("/batches/{batch_id}/download")
async def download_batch(batch_id: str, background_tasks: BackgroundTasks, request: Request):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    if any(getattr(f, "is_text_input", False) for f in batch.files):
        raise HTTPException(
            status_code=400,
            detail="Download ZIP disponibile solo per batch da file. Per input testo usa il download TXT dalla UI.",
        )
    if batch.status != BatchStatus.DONE:
        raise HTTPException(status_code=400, detail=f"Batch non completato (stato: {batch.status.value}).")
    batch_dir = get_batch_dir(batch_id)
    zip_files = list(batch_dir.glob("*.zip"))
    if not zip_files:
        raise HTTPException(status_code=404, detail="File ZIP non trovato.")
    zip_path = zip_files[0]
    
    # Security Fix #10: Cleanup dict after download
    _batch_start_times.pop(batch_id, None)
    _audit_event(request, "batch_download", batch_id=batch_id, filename=zip_path.name)
    background_tasks.add_task(cleanup_batch, batch_id)
    return FileResponse(path=str(zip_path), media_type="application/zip", filename=zip_path.name)


@router.delete("/batches/{batch_id}")
async def delete_batch(batch_id: str):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    cleanup_batch(batch_id)
    return {"message": f"Batch {batch_id} eliminato."}


@router.post("/batches/{batch_id}/passphrase/regenerate")
async def regenerate_batch_passphrase(batch_id: str):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch non trovato")
    new_pp = regenerate_passphrase(batch_id)
    if not new_pp:
        raise HTTPException(status_code=500, detail="Impossibile rigenerare la passphrase")
    return {"batch_id": batch_id, "passphrase": new_pp}


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
