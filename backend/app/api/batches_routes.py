"""
Router API per i flussi batches (upload file e gestione ciclo di vita).
Separato dal router monolitico per ridurre blast radius e accoppiamento.
"""

import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.audit import audit_event, scrub_sensitive
from app.core.batch_manager import (
    cleanup_batch,
    create_batch,
    generate_passphrase,
    get_batch,
    get_batch_dir,
    get_decisions,
    get_passphrase,
    list_batches,
    regenerate_passphrase,
    store_decisions,
    store_passphrase,
    update_batch,
    set_batch_start_time,
    get_batch_start_time,
    clear_batch_start_time,
)
from app.core.config import (
    CONFIG_DIR,
    MAX_FILE_SIZE_BYTES,
    MAX_UPLOAD_FILES_PER_BATCH,
    SUPPORTED_EXTENSIONS,
)
from app.core.pipeline import apply_review_decisions
from app.core.policies import get_enabled_entity_types, get_policy
from app.core.rate_limit import enforce_rate_limit
from app.core.auth import validate_csrf_dependency
from app.core.tasks import apply_batch_task, get_task_status, scan_batch_task
from app.models.schemas import (
    Batch,
    BatchConfig,
    BatchMode,
    BatchStatus,
    FileRecord,
    FileStatus,
    PresetName,
    ReviewAction,
    SafetyLabel,
    SubmitReviewRequest,
)
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# File di stato server-side (no password, no PII)
_STATE_FILE = CONFIG_DIR / "state.json"


def _sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitizza filename per upload sicuro.
    
    Security Fix #C2: Filename sanitization
    - Rimuove null bytes
    - Normalizza Unicode (NFC)
    - Whitelist: alphanumeric, dots, dash, underscore, space
    - Rimuove leading dots (hidden files)
    - Max length 200 caratteri
    - Empty fallback to UUID
    """
    import re
    import uuid
    import unicodedata
    
    # Remove null bytes
    filename = filename.replace('\x00', '')
    
    # Normalize Unicode (decompose + recompose to prevent attack via combining chars)
    filename = unicodedata.normalize('NFC', filename)
    
    # Whitelist: allow only safe characters
    # Keep alphanumerics, dots, dash, underscore, space
    safe = re.sub(r'[^a-zA-Z0-9._\-\s]', '_', filename)
    
    # Remove leading dots (prevent hidden files)
    safe = safe.lstrip('.')
    
    # Ensure not empty
    if not safe or safe.isspace():
        safe = f"file_{uuid.uuid4().hex[:8]}"
    
    # Limit length (filesystem max is 255, keep margin)
    if len(safe) > max_length:
        name_part, ext_part = Path(safe).stem, Path(safe).suffix
        safe = name_part[:max_length - len(ext_part)] + ext_part
    
    logger.debug("Filename sanitized: %r → %r", filename, safe)
    return safe


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
    Security Fix #C1: Specific exception handling (was bare except)
    """
    try:
        from app.core.config import MIN_PASSPHRASE_ENTROPY, MIN_PASSPHRASE_LENGTH
    except (ImportError, AttributeError) as e:
        logger.warning("Failed to import passphrase config: %s. Using defaults.", e)
        MIN_PASSPHRASE_LENGTH = 12
        MIN_PASSPHRASE_ENTROPY = 2.5

    if not passphrase or len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"La passphrase deve essere di almeno {MIN_PASSPHRASE_LENGTH} caratteri.",
        )

    entropy = _calculate_entropy(passphrase)
    if entropy < MIN_PASSPHRASE_ENTROPY:
        raise HTTPException(
            status_code=400,
            detail=f"La passphrase è troppo debole (entropia: {entropy:.2f} bits/char, minimo: {MIN_PASSPHRASE_ENTROPY}). "
            "Usa caratteri variati e non ripetitivi.",
        )


def _validate_file_magic_bytes(content: bytes, filename: str) -> str:
    """
    Valida il magic bytes del file per verificare che corrisponda all'estensione.
    Security Fix #3: Malicious file detection
    Restituisce l'estensione rilevata.
    """
    ext = Path(filename).suffix.lower()

    if content.startswith(b"%PDF"):
        detected_ext = ".pdf"
    elif content.startswith(b"PK\x03\x04"):
        if b"word/" in content[:2000]:
            detected_ext = ".docx"
        elif b"xl/" in content[:2000]:
            detected_ext = ".xlsx"
        else:
            detected_ext = ".zip"
    elif content.startswith(b"\xff\xd8\xff"):
        detected_ext = ".jpg"
    elif content.startswith(b"\x89PNG"):
        detected_ext = ".png"
    else:
        if ext in {".txt", ".md", ".csv"}:
            detected_ext = ext
        else:
            detected_ext = None

    if detected_ext != ext and ext in SUPPORTED_EXTENSIONS:
        logger.warning(f"Mismatch magic bytes per {filename}: dichiarato {ext}, rilevato {detected_ext}")

    return detected_ext


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


# Helper functions moved to app.core.audit module


# ─── Batch Input Validation & File Processing (Helper Functions) ───────────────


def _validate_upload_input(
    files: List[UploadFile],
    mode: str,
    preset: str,
    passphrase: str,
) -> Tuple[BatchMode, PresetName]:
    """
    Valida e trasforma input del batch.
    Solleva HTTPException se non valido.
    """
    if len(files) > MAX_UPLOAD_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Massimo {MAX_UPLOAD_FILES_PER_BATCH} file per batch.",
        )

    if passphrase:
        _validate_passphrase(passphrase)

    # ✅ FIX #4a: Validate mode strictly - don't silently default
    try:
        batch_mode = BatchMode(mode.lower())
    except ValueError:
        valid_modes = ", ".join([m.value for m in BatchMode])
        raise HTTPException(
            status_code=400,
            detail=f"Modalità non valida: '{mode}'. Valide: {valid_modes}",
        )

    # ✅ FIX #4b: Validate preset - _resolve_preset already raises on invalid
    batch_preset = _resolve_preset(preset)
    return batch_mode, batch_preset


async def _process_uploaded_files(
    batch_id: str,
    files: List[UploadFile],
) -> Tuple[int, List[str], List]:
    """
    Processa i file caricati: validazione, storage, deduplica.
    Restituisce (files_stored_count, warning_messages, file_records).
    """
    batch_dir = get_batch_dir(batch_id)
    upload_dir = batch_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    files_stored = 0
    warnings = []
    file_records = []

    for upload_file in files:
        if not upload_file.filename:
            continue

        file_path = Path(upload_file.filename)
        ext = file_path.suffix.lower()

        # Validazione estensione
        if ext not in SUPPORTED_EXTENSIONS:
            logger.warning("File ignorato (formato non supportato): %s", upload_file.filename)
            warnings.append(f"File '{upload_file.filename}': formato non supportato")
            continue

        # Validazione dimensione
        content = await upload_file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            logger.warning("File troppo grande: %s (%d bytes)", upload_file.filename, len(content))
            warnings.append(f"File '{upload_file.filename}': dimensione > {MAX_FILE_SIZE_BYTES} bytes")
            continue

        # Validazione magic bytes
        try:
            detected_ext = _validate_file_magic_bytes(content, upload_file.filename)
            if detected_ext not in SUPPORTED_EXTENSIONS:
                logger.warning("File ignorato (magic bytes non corrisponde): %s", upload_file.filename)
                warnings.append(f"File '{upload_file.filename}': magic bytes non corrispondono")
                continue
        except Exception as e:
            logger.warning("Errore validazione magic bytes per %s: %s", upload_file.filename, e)
            warnings.append(f"File '{upload_file.filename}': errore validazione {e}")
            continue

        # Storage con deduplicazione
        # ✅ FIX #C2: Use sanitized filename
        safe_name = _sanitize_filename(file_path.name)
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
        file_records.append(file_rec)
        files_stored += 1

    return files_stored, warnings, file_records


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
    Orchestrazione: validazione → creazione batch → caricamento file → scansione.
    """
    rate_info = enforce_rate_limit(request, "batch_create", limit=20)

    # Step 1: Validazione input
    batch_mode, batch_preset = _validate_upload_input(files, mode, preset, passphrase)

    # Step 2: Creazione batch e storage passphrase
    config = BatchConfig(mode=batch_mode, preset=batch_preset)
    batch = Batch(config=config)
    batch = create_batch(batch)
    pp = passphrase if passphrase else generate_passphrase()
    store_passphrase(batch.batch_id, pp)
    set_batch_start_time(batch.batch_id)  # ✅ FIX #3: Thread-safe timing

    # Step 3: Caricamento file (con validazione)
    files_stored, warnings, file_records = await _process_uploaded_files(batch.batch_id, files)
    batch.files = file_records

    # Step 4: Verifica batch non vuoto
    if not batch.files:
        cleanup_batch(batch.batch_id)
        raise HTTPException(
            status_code=400,
            detail="Nessun file valido caricato. Formati supportati: " + ", ".join(sorted(SUPPORTED_EXTENSIONS)),
        )

    update_batch(batch)
    set_batch_start_time(batch.batch_id)  # ✅ FIX #3: Update timing

    # Step 5: Enqueue async scan task (non-blocking)
    batch.status = BatchStatus.SCANNING
    update_batch(batch)
    scan_task = scan_batch_task.delay(batch.batch_id)
    batch.task_id = scan_task.id
    update_batch(batch)

    # Step 6: Audit log
    audit_event(
        request,
        "batch_scan_queued",
        batch_id=batch.batch_id,
        task_id=scan_task.id,
        files_count=len(batch.files),
    )

    return JSONResponse(
        status_code=202,
        content={
            "batch_id": batch.batch_id,
            "status": batch.status.value,
            "task_id": scan_task.id,
            "mode": mode,
            "passphrase": pp,
            "files": [{"name": fr.original_name, "id": fr.file_id} for fr in batch.files],
            "findings": [],
            "findings_count": 0,
            "safety_label": batch.safety_label.value if batch.safety_label else "SAFE_TO_UPLOAD",
            "message": "Scansione accodata. Usa GET /api/batches/{batch_id} per lo stato.",
        },
        headers={
            "X-RateLimit-Limit": str(rate_info["limit"]),
            "X-RateLimit-Remaining": str(rate_info["remaining"]),
            "X-RateLimit-Reset": str(rate_info["reset"]),
        }
    )


# ─── Batch Lifecycle ──────────────────────────────────────────────────────────


@router.get("/batches")
async def list_all_batches():
    """Lista tutti i batch attivi con metadata (senza findings completi)."""
    batches = list_batches()
    result = []
    for b in batches:
        result.append(
            {
                "batch_id": b.batch_id,
                "status": b.status.value,
                "mode": b.config.mode.value,
                "files_count": len(b.files),
                "findings_count": len(b.findings),
                "safety_label": b.safety_label.value if b.safety_label else "SAFE_TO_UPLOAD",
                "created_at": b.created_at if hasattr(b, "created_at") else None,
            }
        )
    return {"batches": result, "total": len(result)}


@router.get("/batches/{batch_id}")
async def get_batch_status(batch_id: str):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    return {
        "batch_id": batch.batch_id,
        "status": batch.status.value,
        "task_id": batch.task_id,
        "files": [{"name": fr.original_name, "id": fr.file_id} for fr in batch.files],
        "findings": _findings_list(batch),
        "findings_count": len(batch.findings),
        "safety_label": batch.safety_label.value if batch.safety_label else "SAFE_TO_UPLOAD",
        "error_message": batch.error_message,
    }


@router.get("/batches/{batch_id}/status")
async def get_batch_task_status(batch_id: str):
    """
    Endpoint lightweight per polling async.
    Restituisce solo stato task/batch senza findings completi.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    if not batch.task_id:
        return {
            "batch_id": batch.batch_id,
            "task_id": None,
            "status": batch.status.value,
            "task_state": "NOT_QUEUED",
            "error_message": batch.error_message,
        }

    task_info = get_task_status(batch.task_id)
    task_state = str(task_info.get("status", "UNKNOWN")).upper()

    if task_state == "FAILURE":
        status = "error"
    elif task_state in {"PENDING", "RECEIVED"}:
        status = "pending"
    elif task_state in {"STARTED", "RETRY"}:
        status = "running"
    elif task_state == "SUCCESS":
        status = batch.status.value
    else:
        status = batch.status.value

    return {
        "batch_id": batch.batch_id,
        "task_id": batch.task_id,
        "status": status,
        "task_state": task_state,
        "error_message": batch.error_message or task_info.get("error"),
        "result": task_info.get("result") if task_state == "SUCCESS" else None,
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
    if batch.status not in (BatchStatus.REVIEW, BatchStatus.DONE, BatchStatus.DONE_WITH_ERRORS):
        raise HTTPException(
            status_code=400,
            detail=f"Batch non in review (stato: {batch.status.value}).",
        )

    decisions_dicts = []
    for d in review_request.decisions:
        decisions_dicts.append(
            {
                "finding_id": d.finding_id,
                "action": d.action.value if hasattr(d.action, "value") else str(d.action),
                "custom_pseudonym": d.modified_pseudonym,
            }
        )
    counts = store_decisions(batch_id, decisions_dicts)

    batch = apply_review_decisions(batch_id, review_request.decisions)

    audit_event(
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
    ✅ FIX #5: Added error handling with state rollback on failure.
    """
    rate_info = enforce_rate_limit(request, "batch_apply", limit=20)

    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")
    if batch.status != BatchStatus.REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Batch non in review (stato: {batch.status.value}).",
        )

    # ✅ CRITICAL FIX #4: Validate passphrase exists before applying
    # Prevents silent failures when zip download would fail due to missing passphrase
    passphrase = get_passphrase(batch_id)
    if not passphrase:
        raise HTTPException(
            status_code=410,  # 410 Gone - passphrase has been lost/cleared
            detail="Passphrase persa: il batch è stato ripulito. Ricrea il batch e ripeti la scansione.",
        )

    decisions_map = get_decisions(batch_id)
    if decisions_map:
        from app.models.schemas import ReviewDecisionItem

        decision_items = []
        for fid, dec in decisions_map.items():
            try:
                action = ReviewAction(dec["action"])
            except (ValueError, KeyError):
                action = ReviewAction.ACCEPT
            decision_items.append(
                ReviewDecisionItem(
                    finding_id=fid,
                    action=action,
                    modified_pseudonym=dec.get("custom_pseudonym"),
                )
            )
        apply_review_decisions(batch_id, decision_items)

    # Use thread-safe function instead of direct dict access
    started_at = get_batch_start_time(batch_id) or datetime.now(timezone.utc).isoformat()

    batch.status = BatchStatus.APPLYING
    update_batch(batch)
    apply_task = apply_batch_task.delay(batch_id, started_at)
    batch.task_id = apply_task.id
    update_batch(batch)

    decisions_count = len(decisions_map)
    rejected_count = sum(1 for d in decisions_map.values() if str(d.get("action", "")).lower() == "reject")
    modified_count = sum(1 for d in decisions_map.values() if str(d.get("action", "")).lower() == "modify")
    accepted_count = decisions_count - rejected_count - modified_count
    ignored_count = rejected_count

    audit_event(
        request,
        "batch_apply_queued",
        batch_id=batch_id,
        task_id=apply_task.id,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        modified_count=modified_count,
    )

    return JSONResponse(
        status_code=202,
        content={
            "message": "Apply accodato. Usa GET /api/batches/{batch_id} per lo stato.",
            "batch_id": batch_id,
            "task_id": apply_task.id,
            "download_ready": False,
            "decisions_received_count": decisions_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "modified_count": modified_count,
            "ignored_count": ignored_count,
        },
        headers={
            "X-RateLimit-Limit": str(rate_info["limit"]),
            "X-RateLimit-Remaining": str(rate_info["remaining"]),
            "X-RateLimit-Reset": str(rate_info["reset"]),
        }
    )


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
    if batch.status == BatchStatus.DONE_WITH_ERRORS:
        raise HTTPException(
            status_code=409,
            detail="Export bloccato: il batch contiene errori di trasformazione (status=done_with_errors).",
        )
    if batch.status != BatchStatus.DONE:
        raise HTTPException(status_code=400, detail=f"Batch non completato (stato: {batch.status.value}).")
    if batch.safety_label != SafetyLabel.SAFE_TO_UPLOAD:
        raise HTTPException(
            status_code=409,
            detail=("Export bloccato: safety_label non sicura " f"({batch.safety_label.value})."),
        )
    batch_dir = get_batch_dir(batch_id)
    zip_files = list(batch_dir.glob("*.zip"))
    if not zip_files:
        raise HTTPException(status_code=404, detail="File ZIP non trovato.")
    zip_path = zip_files[0]

    # ✅ FIX #16: Log performance metrics when batch completes
    started_at_iso = clear_batch_start_time(batch_id)  # ✅ FIX #3: Thread-safe clear
    if started_at_iso:
        try:
            started_at = datetime.fromisoformat(started_at_iso)
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info("Batch %s completed in %.2f seconds", batch_id, elapsed)
        except Exception as e:
            logger.warning("Failed to calculate batch timing: %s", e)
    audit_event(request, "batch_download", batch_id=batch_id, filename=zip_path.name)
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
