"""
Pipeline principale di orchestrazione del processo di pseudonimizzazione.
Coordina: parsing -> detection -> pseudonimizzazione -> trasformazione -> report.
"""
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from app.models.schemas import (
    Batch, BatchStatus, FileRecord, FileStatus, Finding,
    ReviewDecisionItem, ReviewAction, BatchMode
)
from app.core.batch_manager import get_batch, update_batch, get_batch_dir, get_passphrase
from app.parsers.factory import parse_file
from app.parsers.base import ParseResult
from app.detectors.engine import detect_in_parse_result
from app.pseudonymizer.engine import PseudonymEngine
from app.pseudonymizer.transformer import transform_file
from app.mapping.crypto import save_encrypted_mapping
from app.report.generator import build_report_data, generate_json_report, generate_html_report

logger = logging.getLogger(__name__)

# Store dei ParseResult in memoria (per la fase di trasformazione)
_parse_results: Dict[str, ParseResult] = {}


def run_scan_pipeline(batch_id: str) -> Batch:
    """
    Fase 1: Parsing e Detection.
    Processa tutti i file del batch e popola la lista dei findings.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

    batch.status = BatchStatus.SCANNING
    update_batch(batch)

    batch_dir = get_batch_dir(batch_id)
    engine = PseudonymEngine(mode=batch.config.mode)
    all_findings: List[Finding] = []

    for file_rec in batch.files:
        file_path = Path(file_rec.stored_path)
        logger.info("Processing file: %s", file_rec.original_name)

        # 1. Parsing
        parse_result = parse_file(file_path)
        _parse_results[file_rec.file_id] = parse_result

        if not parse_result.success:
            file_rec.status = FileStatus.FAILED
            file_rec.error_message = parse_result.error_message
            logger.warning("Parsing fallito per '%s': %s", file_rec.original_name, parse_result.error_message)
            continue

        # Aggiungi i warning del parser al file record
        file_rec.warnings.extend(parse_result.warnings)

        # 2. Detection
        raw_findings = detect_in_parse_result(parse_result)

        # 3. Pseudonimizzazione (genera pseudonimi proposti)
        file_findings = engine.process_findings(raw_findings, file_rec.file_id)
        file_rec.findings_count = len(file_findings)
        all_findings.extend(file_findings)

        file_rec.status = FileStatus.PARSED
        logger.info(
            "File '%s' processato: %d finding trovati.",
            file_rec.original_name, len(file_findings)
        )

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
            if decision.action == ReviewAction.MODIFY and decision.modified_pseudonym:
                finding.modified_pseudonym = decision.modified_pseudonym

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
