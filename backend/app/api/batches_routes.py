"""
Router API per i flussi batches (upload file e gestione ciclo di vita).
Separato dal router monolitico per ridurre blast radius e accoppiamento.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

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
)
from app.core.config import (
    API_HEAVY_TIMEOUT_SECONDS,
    CONFIG_DIR,
    MAX_FILE_SIZE_BYTES,
    MAX_UPLOAD_FILES_PER_BATCH,
    SUPPORTED_EXTENSIONS,
)
from app.core.pipeline import apply_review_decisions, run_apply_pipeline, run_scan_pipeline
from app.core.policies import get_enabled_entity_types, get_policy
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

import json
import math


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
_rate_buckets: Dict[str, List[float]] = {}
_batch_start_times: dict = {}

# File di stato server-side (no password, no PII)
_STATE_FILE = CONFIG_DIR / "state.json"


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
    try:
        from app.core.config import MIN_PASSPHRASE_LENGTH, MIN_PASSPHRASE_ENTROPY
    except:
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
            detail=f"Massimo {MAX_UPLOAD_FILES_PER_BATCH} file per batch.",
        )

    if passphrase:
        _validate_passphrase(passphrase)

    try:
        batch_mode = BatchMode(mode.lower())
    except ValueError:
        batch_mode = BatchMode.STRICT

    batch_preset = _resolve_preset(preset)

    config = BatchConfig(mode=batch_mode, preset=batch_preset)
    batch = Batch(config=config)
    batch = create_batch(batch)
    pp = passphrase if passphrase else generate_passphrase()
    store_passphrase(batch.batch_id, pp)
    _batch_start_times[batch.batch_id] = datetime.now(timezone.utc).isoformat()

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
            detail="Nessun file valido caricato. Formati supportati: " + ", ".join(sorted(SUPPORTED_EXTENSIONS)),
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
            detail=f"Batch non in review (stato: {batch.status.value}).",
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

    decisions_count = len(decisions_map)
    rejected_count = sum(1 for d in decisions_map.values() if str(d.get("action", "")).lower() == "reject")
    modified_count = sum(1 for d in decisions_map.values() if str(d.get("action", "")).lower() == "modify")
    accepted_count = decisions_count - rejected_count - modified_count
    ignored_count = rejected_count

    _audit_event(
        request,
        "batch_apply_completed",
        batch_id=batch_id,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        modified_count=modified_count,
    )

    updated_batch = get_batch(batch_id)
    download_ready = bool(
        updated_batch and updated_batch.status == BatchStatus.DONE and updated_batch.safety_label == SafetyLabel.SAFE_TO_UPLOAD
    )

    return {
        "message": "Trasformazioni applicate.",
        "batch_id": batch_id,
        "download_ready": download_ready,
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
            detail=(
                "Export bloccato: safety_label non sicura "
                f"({batch.safety_label.value})."
            ),
        )
    batch_dir = get_batch_dir(batch_id)
    zip_files = list(batch_dir.glob("*.zip"))
    if not zip_files:
        raise HTTPException(status_code=404, detail="File ZIP non trovato.")
    zip_path = zip_files[0]

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
