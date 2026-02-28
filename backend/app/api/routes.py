"""
Router API principale per il Local Pseudonymization Tool.
Espone gli endpoint RESTful per la gestione dei batch.
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from app.models.schemas import (
    Batch, BatchConfig, BatchMode, BatchStatus,
    BatchStatusResponse, FindingsResponse,
    SubmitReviewRequest, CreateBatchRequest,
)
from app.core.batch_manager import (
    create_batch, get_batch, update_batch,
    get_batch_dir, store_passphrase, cleanup_batch,
)
from app.core.pipeline import run_scan_pipeline, apply_review_decisions, run_apply_pipeline
from app.core.config import SUPPORTED_EXTENSIONS, MAX_FILE_SIZE_BYTES

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

# Store per i timestamp di avvio dei batch
_batch_start_times: dict = {}


@router.post("/batches", response_model=BatchStatusResponse)
async def create_new_batch(
    files: List[UploadFile] = File(...),
    mode: str = Form("light"),
    is_dry_run: bool = Form(False),
    passphrase: str = Form(...),
):
    """
    Crea un nuovo batch, carica i file e li salva nella directory temporanea.
    """
    if not passphrase or len(passphrase) < 4:
        raise HTTPException(status_code=400, detail="La passphrase deve essere di almeno 4 caratteri.")

    # Valida la modalità
    try:
        batch_mode = BatchMode(mode.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Modalità non valida: '{mode}'. Usa 'light' o 'strict'.")

    # Crea il batch
    config = BatchConfig(mode=batch_mode, is_dry_run=is_dry_run)
    batch = Batch(config=config)
    batch = create_batch(batch)

    # Memorizza la passphrase in memoria
    store_passphrase(batch.batch_id, passphrase)

    batch_dir = get_batch_dir(batch.batch_id)
    upload_dir = batch_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Salva i file caricati
    for upload_file in files:
        if not upload_file.filename:
            continue

        file_path = Path(upload_file.filename)
        ext = file_path.suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            logger.warning("File ignorato (formato non supportato): %s", upload_file.filename)
            continue

        # Leggi e salva il file
        content = await upload_file.read()

        if len(content) > MAX_FILE_SIZE_BYTES:
            logger.warning("File troppo grande ignorato: %s (%d bytes)", upload_file.filename, len(content))
            continue

        safe_name = Path(upload_file.filename).name
        dest_path = upload_dir / safe_name

        # Gestisci duplicati
        counter = 1
        while dest_path.exists():
            dest_path = upload_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
            counter += 1

        dest_path.write_bytes(content)

        from app.models.schemas import FileRecord
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

    return BatchStatusResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        files=batch.files,
        findings_count=0,
    )


@router.post("/batches/{batch_id}/scan", response_model=BatchStatusResponse)
async def scan_batch(batch_id: str):
    """
    Avvia la pipeline di scansione (parsing + detection + pseudonimizzazione proposta).
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    if batch.status not in (BatchStatus.PENDING,):
        raise HTTPException(
            status_code=400,
            detail=f"Il batch è già in stato '{batch.status.value}'. Non è possibile avviare una nuova scansione."
        )

    _batch_start_times[batch_id] = datetime.utcnow().isoformat()

    try:
        batch = run_scan_pipeline(batch_id)
    except Exception as e:
        logger.error("Errore nella pipeline di scansione per batch %s: %s", batch_id, e)
        batch = get_batch(batch_id)
        if batch:
            batch.status = BatchStatus.ERROR
            batch.error_message = str(e)
            update_batch(batch)
        raise HTTPException(status_code=500, detail=f"Errore durante la scansione: {e}")

    return BatchStatusResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        files=batch.files,
        findings_count=len(batch.findings),
    )


@router.get("/batches/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str):
    """Recupera lo stato corrente di un batch."""
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    return BatchStatusResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        files=batch.files,
        findings_count=len(batch.findings),
        error_message=batch.error_message,
    )


@router.get("/batches/{batch_id}/findings", response_model=FindingsResponse)
async def get_findings(batch_id: str):
    """Recupera tutti i finding di un batch per la review manuale."""
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    if batch.status not in (BatchStatus.REVIEW, BatchStatus.DONE):
        raise HTTPException(
            status_code=400,
            detail=f"Il batch non è ancora in fase di review (stato attuale: {batch.status.value})."
        )

    return FindingsResponse(
        batch_id=batch_id,
        findings=batch.findings,
        total=len(batch.findings),
    )


@router.post("/batches/{batch_id}/review")
async def submit_review(batch_id: str, review_request: SubmitReviewRequest):
    """Invia le decisioni di review dell'utente."""
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    if batch.status != BatchStatus.REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Il batch non è in fase di review (stato attuale: {batch.status.value})."
        )

    batch = apply_review_decisions(batch_id, review_request.decisions)

    return {"message": f"Review applicata: {len(review_request.decisions)} decisioni registrate.", "batch_id": batch_id}


@router.post("/batches/{batch_id}/apply")
async def apply_batch(batch_id: str):
    """
    Applica le trasformazioni e genera gli artefatti finali (file pseudonimizzati, report, mapping).
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    if batch.status != BatchStatus.REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Il batch non è in fase di review (stato attuale: {batch.status.value})."
        )

    started_at = _batch_start_times.get(batch_id, datetime.utcnow().isoformat())

    try:
        zip_path = run_apply_pipeline(batch_id, started_at)
    except Exception as e:
        logger.error("Errore nella pipeline di applicazione per batch %s: %s", batch_id, e)
        raise HTTPException(status_code=500, detail=f"Errore durante l'applicazione: {e}")

    return {
        "message": "Trasformazioni applicate con successo.",
        "batch_id": batch_id,
        "download_ready": True,
    }


@router.get("/batches/{batch_id}/download")
async def download_batch(batch_id: str, background_tasks: BackgroundTasks):
    """
    Scarica l'archivio ZIP con i file pseudonimizzati, i report e il mapping cifrato.
    Dopo il download, la directory temporanea viene pulita.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    if batch.status != BatchStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Il batch non è ancora completato (stato attuale: {batch.status.value})."
        )

    batch_dir = get_batch_dir(batch_id)
    zip_files = list(batch_dir.glob("*.zip"))

    if not zip_files:
        raise HTTPException(status_code=404, detail="File ZIP non trovato. Eseguire prima /apply.")

    zip_path = zip_files[0]

    # Pianifica la pulizia della directory temporanea dopo il download
    background_tasks.add_task(cleanup_batch, batch_id)

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )


@router.get("/batches/{batch_id}/report/json")
async def download_report_json(batch_id: str):
    """Scarica il report in formato JSON."""
    batch = get_batch(batch_id)
    if not batch or batch.status != BatchStatus.DONE:
        raise HTTPException(status_code=404, detail="Report non disponibile.")

    batch_dir = get_batch_dir(batch_id)
    report_path = batch_dir / "report.json"

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="File report.json non trovato.")

    return FileResponse(path=str(report_path), media_type="application/json", filename="report.json")


@router.get("/batches/{batch_id}/report/html")
async def download_report_html(batch_id: str):
    """Scarica il report in formato HTML."""
    batch = get_batch(batch_id)
    if not batch or batch.status != BatchStatus.DONE:
        raise HTTPException(status_code=404, detail="Report non disponibile.")

    batch_dir = get_batch_dir(batch_id)
    report_path = batch_dir / "report.html"

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="File report.html non trovato.")

    return FileResponse(path=str(report_path), media_type="text/html", filename="report.html")


@router.delete("/batches/{batch_id}")
async def delete_batch(batch_id: str):
    """Elimina un batch e pulisce i file temporanei."""
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch non trovato: {batch_id}")

    cleanup_batch(batch_id)
    return {"message": f"Batch {batch_id} eliminato e file temporanei rimossi."}


@router.get("/health")
async def health_check():
    """Endpoint di health check."""
    return {"status": "ok", "service": "Local Pseudonymization Tool", "version": "1.0.0-MVP"}


@router.get("/config/dictionaries")
async def get_dictionaries_status():
    """Restituisce lo stato dei dizionari custom caricati."""
    from app.detectors.dictionary_detector import get_dictionary_detector
    detector = get_dictionary_detector()
    return {
        "loaded_terms": detector.loaded_terms_count,
        "message": f"DictionaryDetector attivo con {detector.loaded_terms_count} termini caricati."
    }


@router.post("/config/dictionaries/reload")
async def reload_dictionaries():
    """Ricarica i dizionari custom dalla directory di configurazione."""
    from app.detectors.dictionary_detector import get_dictionary_detector
    detector = get_dictionary_detector()
    detector.reload()
    return {
        "message": f"Dizionari ricaricati: {detector.loaded_terms_count} termini attivi."
    }
