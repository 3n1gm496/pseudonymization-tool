"""
Router API per i flussi console (testo inline).
Separato dal router monolitico per ridurre blast radius e accoppiamento.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
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
    store_passphrase,
)
from app.core.config import API_HEAVY_TIMEOUT_SECONDS, MAX_CONSOLE_TEXT_CHARS
from app.core.console_pipeline import run_text_apply, run_text_scan
from app.core.pipeline import apply_review_decisions
from app.models.schemas import Batch, BatchConfig, BatchMode, PresetName, ReviewAction


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
_rate_buckets: Dict[str, List[float]] = {}
_batch_start_times: dict = {}


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


# ─── Console Apply Helpers ────────────────────────────────────────────────────

def _process_stored_decisions(batch_id: str) -> None:
    """
    Recupera e applica decisions persistite sulla batch.
    """
    decisions_map = get_decisions(batch_id)
    if not decisions_map:
        return
    
    from app.models.schemas import ReviewDecisionItem
    
    decision_items = []
    for fid, dec in decisions_map.items():
        try:
            action = ReviewAction(dec["action"])
        except (ValueError, KeyError):
            action = ReviewAction.ACCEPT
        decision_items.append(ReviewDecisionItem(
            finding_id=fid,
            action=action,
            modified_pseudonym=dec.get("custom_pseudonym"),
        ))
    
    apply_review_decisions(batch_id, decision_items)


def _generate_and_save_mapping(batch_id: str, file_id: str, passphrase: str) -> None:
    """
    Genera mapping criptato da findings e lo salva.
    Solleva Exception se fallisce.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")
    
    file_findings = [f for f in batch.findings if f.file_id == file_id]
    mapping_data = {"mapping": {}}
    for finding in file_findings:
        if finding.review_action != ReviewAction.REJECT:
            pseudo = finding.final_pseudonym
            canon = finding.canonical_value or finding.original_value
            if pseudo not in mapping_data["mapping"]:
                mapping_data["mapping"][pseudo] = canon
    
    from app.mapping.crypto import save_encrypted_mapping
    
    batch_dir = get_batch_dir(batch_id)
    mapping_path = batch_dir / "mapping.enc"
    save_encrypted_mapping(mapping_data, passphrase, mapping_path)
    logger.info("Console mapping.enc salvato per batch %s", batch_id)


# ─── Console Scan ────────────────────────────────────────────────────────────

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
    Applica sostituzioni al testo inline con decisions persistite.
    Accetta: { batch_id, file_id, text }
    Restituisce: pseudonymized_text, passphrase, safety_label, mapping.
    """
    _enforce_rate_limit(request, "console_apply", limit=30)

    # Step 1: Validazione input
    batch_id = req.get("batch_id")
    file_id = req.get("file_id")
    text = req.get("text", "")

    if not batch_id or not file_id:
        raise HTTPException(status_code=400, detail="batch_id e file_id sono obbligatori")
    if len(text) > MAX_CONSOLE_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Testo troppo lungo ({len(text)} caratteri). Massimo: {MAX_CONSOLE_TEXT_CHARS}.",
        )

    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch non trovato")

    # Step 2: Applica decisioni persistite
    _process_stored_decisions(batch_id)

    # Step 3: Applica pseudonimizzazione su testo
    try:
        pseudo_text, safety, residual_warnings, applied_count = await asyncio.wait_for(
            run_in_threadpool(run_text_apply, batch_id, file_id, text),
            timeout=API_HEAVY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout durante l'applicazione sul testo.")
    except Exception as e:
        logger.error("Errore console/apply batch %s: %s", batch_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    # Step 4: Audit log
    _audit_event(
        request,
        "console_apply_completed",
        batch_id=batch_id,
        file_id=file_id,
        applied_count=applied_count,
        safety_label=safety.value if hasattr(safety, "value") else str(safety),
    )

    # Step 5: Genera e salva mapping criptato
    passphrase = get_passphrase(batch_id)
    try:
        _generate_and_save_mapping(batch_id, file_id, passphrase)
    except Exception as e:
        logger.error("Errore salvataggio mapping per console batch %s: %s", batch_id, e)

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
            detail="File di mapping non disponibile. Assicurati di aver completato l'apply della pseudonimizzazione.",
        )

    _audit_event(request, "console_mapping_download", batch_id=batch_id)
    return FileResponse(
        path=str(mapping_path),
        media_type="application/octet-stream",
        filename=f"mapping_{batch_id[:8]}.enc",
    )