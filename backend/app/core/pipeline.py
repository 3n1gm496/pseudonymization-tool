"""
Pipeline principale di orchestrazione del processo di pseudonimizzazione.
Coordina: parsing -> detection -> pseudonimizzazione -> trasformazione -> report.
"""
import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import List, Dict, Optional

from app.models.schemas import (
    Batch, BatchStatus, FileRecord, FileStatus, Finding,
    ReviewDecisionItem, ReviewAction, BatchMode
)
from app.core.batch_manager import get_batch, update_batch, get_batch_dir, get_passphrase
from app.core.config import (
    STREAMING_THRESHOLD_MB, STREAMING_CHUNK_SIZE,
    PARALLEL_FILE_PROCESSING, MAX_PARALLEL_FILES,
    FILE_PROCESSING_TIMEOUT_SECONDS
)
from app.parsers.factory import parse_file, get_parser
from app.parsers.base import ParseResult, TextChunk
from app.detectors.engine import detect_in_parse_result
from app.pseudonymizer.engine import PseudonymEngine
from app.pseudonymizer.transformer import transform_file
from app.mapping.crypto import save_encrypted_mapping
from app.report.generator import build_report_data, generate_json_report, generate_html_report

logger = logging.getLogger(__name__)

# Store dei ParseResult in memoria (per la fase di trasformazione)
_parse_results: Dict[str, ParseResult] = {}
_parse_results_lock = Lock()


def _should_use_streaming(file_path: Path) -> bool:
    """Verifica se il file è abbastanza grande per streaming."""
    try:
        size_mb = file_path.stat().st_size / (1024 * 1024)
        return size_mb > STREAMING_THRESHOLD_MB
    except Exception:
        return False


def _process_single_file(file_rec: FileRecord, engine: PseudonymEngine) -> tuple[FileRecord, List[Finding], ParseResult]:
    """
    Processa un singolo file: parsing + detection + pseudonimizzazione.
    Ritorna (file_rec aggiornato, findings, parse_result).
    """
    file_path = Path(file_rec.stored_path)
    logger.info("Processing file: %s", file_rec.original_name)

    # 1. Parsing (con streaming per file grandi)
    use_streaming = _should_use_streaming(file_path)
    
    if use_streaming:
        logger.info("File %s > %sMB, usando streaming", file_rec.original_name, STREAMING_THRESHOLD_MB)
        parser = get_parser(file_path)
        
        if parser and hasattr(parser, 'supports_streaming') and parser.supports_streaming():
            # Build ParseResult incrementalmente
            parse_result = ParseResult(file_path=file_path)
            try:
                for chunk in parser.parse_stream(file_path, chunk_size=STREAMING_CHUNK_SIZE):
                    parse_result.chunks.append(chunk)
                parse_result.success = True
            except Exception as e:
                parse_result.success = False
                parse_result.error_message = f"Errore streaming: {e}"
                logger.error("Errore durante streaming di %s: %s", file_rec.original_name, e)
        else:
            # Fallback a parse normale
            parse_result = parse_file(file_path)
    else:
        parse_result = parse_file(file_path)

    if not parse_result.success:
        file_rec.status = FileStatus.FAILED
        file_rec.error_message = parse_result.error_message
        logger.warning("Parsing fallito per '%s': %s", file_rec.original_name, parse_result.error_message)
        return file_rec, [], parse_result

    # Aggiungi i warning del parser al file record
    file_rec.warnings.extend(parse_result.warnings)

    # 2. Detection
    raw_findings = detect_in_parse_result(parse_result)

    # 3. Pseudonimizzazione (genera pseudonimi proposti)
    file_findings = engine.process_findings(raw_findings, file_rec.file_id)
    file_rec.findings_count = len(file_findings)
    file_rec.status = FileStatus.PARSED
    
    logger.info(
        "File '%s' processato: %d finding trovati.",
        file_rec.original_name, len(file_findings)
    )

    return file_rec, file_findings, parse_result


def run_scan_pipeline(batch_id: str) -> Batch:
    """
    Fase 1: Parsing e Detection.
    Processa tutti i file del batch e popola la lista dei findings.
    Supporta elaborazione parallela se PARALLEL_FILE_PROCESSING è abilitato.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

    batch.status = BatchStatus.SCANNING
    update_batch(batch)

    batch_dir = get_batch_dir(batch_id)
    engine = PseudonymEngine(mode=batch.config.mode)
    all_findings: List[Finding] = []

    if PARALLEL_FILE_PROCESSING and len(batch.files) > 1:
        # Elaborazione parallela
        logger.info("Elaborazione parallela di %d file (max %d workers)", len(batch.files), MAX_PARALLEL_FILES)
        
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_FILES) as executor:
            # Sottometti tutti i file per l'elaborazione
            future_to_file = {
                executor.submit(_process_single_file, file_rec, engine): file_rec
                for file_rec in batch.files
            }
            
            # Raccogli i risultati man mano che completano
            for future in as_completed(future_to_file, timeout=FILE_PROCESSING_TIMEOUT_SECONDS * len(batch.files)):
                file_rec = future_to_file[future]
                try:
                    # Timeout per singolo file
                    updated_file_rec, file_findings, parse_result = future.result(timeout=FILE_PROCESSING_TIMEOUT_SECONDS)
                    
                    # Aggiorna il file record nel batch
                    for i, f in enumerate(batch.files):
                        if f.file_id == updated_file_rec.file_id:
                            batch.files[i] = updated_file_rec
                            break
                    
                    # Salva il parse result e i findings (thread-safe)
                    with _parse_results_lock:
                        _parse_results[updated_file_rec.file_id] = parse_result
                    all_findings.extend(file_findings)
                
                except TimeoutError:
                    logger.error("Timeout durante elaborazione di %s (>%ds)", file_rec.original_name, FILE_PROCESSING_TIMEOUT_SECONDS)
                    file_rec.status = FileStatus.FAILED
                    file_rec.error_message = f"Timeout: elaborazione superata {FILE_PROCESSING_TIMEOUT_SECONDS}s"
                except Exception as e:
                    logger.error("Errore durante elaborazione parallela di %s: %s", file_rec.original_name, e)
                    file_rec.status = FileStatus.FAILED
                    file_rec.error_message = f"Errore parallelo: {e}"
    else:
        # Elaborazione sequenziale (fallback o batch con 1 file)
        logger.info("Elaborazione sequenziale di %d file", len(batch.files))
        
        for file_rec in batch.files:
            try:
                updated_file_rec, file_findings, parse_result = _process_single_file(file_rec, engine)
                
                # Aggiorna il file record
                for i, f in enumerate(batch.files):
                    if f.file_id == updated_file_rec.file_id:
                        batch.files[i] = updated_file_rec
                        break
                
                with _parse_results_lock:
                    _parse_results[updated_file_rec.file_id] = parse_result
                all_findings.extend(file_findings)
                
            except Exception as e:
                logger.error("Errore durante elaborazione di %s: %s", file_rec.original_name, e)
                file_rec.status = FileStatus.FAILED
                file_rec.error_message = f"Errore: {e}"

    # Aggiorna il batch con tutti i findings
    batch.findings = all_findings
    batch.status = BatchStatus.REVIEW
    update_batch(batch)

    logger.info(
        "Scansione completata per batch %s: %d finding totali in %d file.",
        batch_id, len(all_findings), len(batch.files)
    )
    return batch


def apply_review_decisions(batch_id: str, decisions: List[ReviewDecisionItem]) -> Batch:
    """
    Applica le decisioni di review dell'utente ai finding del batch.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

    # Crea una mappa finding_id -> decisione
    decision_map = {d.finding_id: d for d in decisions}

    for finding in batch.findings:
        if finding.finding_id in decision_map:
            decision = decision_map[finding.finding_id]
            finding.review_action = decision.action
            if decision.action == ReviewAction.MODIFY:
                # Use sanitized pseudonym to prevent injection attacks
                sanitized = decision.sanitized_pseudonym()
                if sanitized:
                    finding.modified_pseudonym = sanitized
                else:
                    logger.warning(f"Modified pseudonym vuoto o invalido per finding {finding.finding_id}, ignorato")

    update_batch(batch)
    return batch


def run_apply_pipeline(batch_id: str, started_at: str) -> Path:
    """
    Fase 2: Trasformazione e Generazione Output.
    Applica le sostituzioni ai file e genera report e mapping cifrato.
    Restituisce il percorso del file ZIP con tutti gli artefatti.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

    batch.status = BatchStatus.APPLYING
    update_batch(batch)

    batch_dir = get_batch_dir(batch_id)
    output_dir = batch_dir / "output"
    output_dir.mkdir(exist_ok=True)

    passphrase = get_passphrase(batch_id)

    # Raggruppa i finding per file
    findings_by_file: Dict[str, List[Finding]] = {}
    for finding in batch.findings:
        if finding.file_id not in findings_by_file:
            findings_by_file[finding.file_id] = []
        findings_by_file[finding.file_id].append(finding)

    # Se dry-run, non applicare trasformazioni
    if not batch.config.is_dry_run:
        for file_rec in batch.files:
            if file_rec.status == FileStatus.FAILED:
                continue

            file_path = Path(file_rec.stored_path)
            file_findings = findings_by_file.get(file_rec.file_id, [])
            
            with _parse_results_lock:
                parse_result = _parse_results.get(file_rec.file_id)

            try:
                output_path, transform_warnings = transform_file(
                    original_path=file_path,
                    output_dir=output_dir,
                    findings=file_findings,
                    parse_result=parse_result,
                )
                file_rec.warnings.extend(transform_warnings)
                file_rec.status = FileStatus.PROCESSED
            except Exception as e:
                file_rec.status = FileStatus.FAILED
                file_rec.error_message = f"Errore durante la trasformazione: {e}"
                logger.error("Errore trasformazione '%s': %s", file_rec.original_name, e)

    # Genera il mapping cifrato
    completed_at = datetime.utcnow().isoformat()

    if passphrase and not batch.config.is_dry_run:
        # Costruisci la mappa di reversibilità
        mapping_data = {
            "batch_id": batch_id,
            "created_at": completed_at,
            "mode": batch.config.mode.value,
            "mapping": {}
        }
        for finding in batch.findings:
            if finding.review_action != ReviewAction.REJECT:
                pseudo = finding.final_pseudonym
                original = finding.original_value
                if pseudo not in mapping_data["mapping"]:
                    mapping_data["mapping"][pseudo] = original

        mapping_path = batch_dir / "mapping.enc"
        try:
            save_encrypted_mapping(mapping_data, passphrase, mapping_path)
        except Exception as e:
            logger.error("Errore nella cifratura del mapping: %s", e)

    # Genera i report
    report_data = build_report_data(
        batch=batch,
        findings=batch.findings,
        started_at=started_at,
        completed_at=completed_at,
    )

    report_json_path = batch_dir / "report.json"
    report_html_path = batch_dir / "report.html"
    generate_json_report(report_data, report_json_path)
    generate_html_report(report_data, report_html_path)

    # Crea l'archivio ZIP finale
    zip_path = batch_dir / f"pseudonymized_batch_{batch_id[:8]}.zip"
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        # File pseudonimizzati
        if output_dir.exists():
            for output_file in output_dir.iterdir():
                zf.write(str(output_file), f"files/{output_file.name}")

        # Report
        if report_json_path.exists():
            zf.write(str(report_json_path), "report.json")
        if report_html_path.exists():
            zf.write(str(report_html_path), "report.html")

        # Mapping cifrato
        mapping_path = batch_dir / "mapping.enc"
        if mapping_path.exists():
            zf.write(str(mapping_path), "mapping.enc")

    batch.status = BatchStatus.DONE
    update_batch(batch)

    logger.info("Pipeline completata per batch %s. ZIP: %s", batch_id, zip_path)
    return zip_path
