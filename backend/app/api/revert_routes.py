"""
Router API per i flussi di revert (ZIP e testo).
Separato dal router monolitico per ridurre blast radius e accoppiamento.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.audit import audit_event, scrub_sensitive
from app.core.config import MAX_CONSOLE_TEXT_CHARS, MAX_FILE_SIZE_BYTES
from app.core.rate_limit import enforce_rate_limit
from app.core.auth import validate_csrf_dependency
from app.core.revert import apply_revert, apply_revert_text, preview_revert, preview_revert_text
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# Helper functions moved to app.core.audit module


@router.post("/revert/preview")
async def revert_preview(
    request: Request,
    archive: UploadFile = File(...),
    passphrase: str = Form(...),
):
    enforce_rate_limit(request, "revert_preview", limit=15)
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

    audit_event(
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
    enforce_rate_limit(request, "revert_apply", limit=10)
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
    audit_event(
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
    enforce_rate_limit(request, "revert_text_preview", limit=25)
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

    audit_event(
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
    enforce_rate_limit(request, "revert_text_apply", limit=25)
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

    audit_event(
        request,
        "revert_text_apply",
        mapping_name=mapping_file.filename,
        input_chars=len(text),
        total_replacements=result.get("total_replacements", 0),
    )
    return result
