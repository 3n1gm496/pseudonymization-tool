"""
Pipeline principale di orchestrazione del processo di pseudonimizzazione v2.
Coordina: parsing -> detection -> pseudonimizzazione -> trasformazione -> report.
Usa PseudonymEngine persistente per batch, canonical_value, policy hash, safety label.
"""
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from app.models.schemas import (
    Batch, BatchStatus, FileRecord, FileStatus, Finding,
    ReviewDecisionItem, ReviewAction, BatchMode, SafetyLabel, PresetName
)
from app.core.batch_manager import (
    get_batch, update_batch, get_batch_dir, get_passphrase,
    get_or_create_engine, get_engine,
)
from app.core.policies import get_policy_hash, get_enabled_entity_types, get_confidence_threshold
from app.core.safety import compute_safety_label, compute_residual_warnings
from app.parsers.factory import parse_file
from app.parsers.base import ParseResult
from app.detectors.engine import detect_in_parse_result, residual_scan, build_extra_detectors
from app.pseudonymizer.transformer import transform_file
from app.mapping.crypto import save_encrypted_mapping
from app.report.generator import build_report_data, generate_json_report, generate_html_report

logger = logging.getLogger(__name__)

# Store dei ParseResult in memoria (per la fase di trasformazione)
_parse_results: Dict[str, Dict[str, ParseResult]] = {}


def _cache_parse_result(batch_id: str, file_id: str, parse_result: ParseResult) -> None:
    batch_cache = _parse_results.setdefault(batch_id, {})
    batch_cache[file_id] = parse_result


def _get_parse_result(batch_id: str, file_id: str) -> Optional[ParseResult]:
    return _parse_results.get(batch_id, {}).get(file_id)


def _clear_parse_results(batch_id: str) -> None:
    _parse_results.pop(batch_id, None)


def _filter_findings_by_policy(
    findings: List[Finding],
    preset: PresetName,
) -> List[Finding]:
    """Filtra i finding in base alla policy: tipi abilitati e soglia di confidenza."""
    enabled = set(get_enabled_entity_types(preset))
    threshold = get_confidence_threshold(preset)
    return [
        f for f in findings
        if f.entity_type.value in enabled and f.confidence_score >= threshold
    ]


def run_scan_pipeline(batch_id: str) -> Batch:
    """
    Fase 1: Parsing e Detection.
    Processa tutti i file del batch e popola la lista dei findings.
    Usa il PseudonymEngine persistente del batch per garantire consistenza.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

    batch.status = BatchStatus.SCANNING
    update_batch(batch)

    # Engine persistente per il batch
    engine = get_or_create_engine(batch_id, batch.config.mode)

    # Extra detectors (LDAP, domain fragments) basati sulla policy
    from app.core.policies import is_ldap_enabled_for_preset
    ldap_enabled = is_ldap_enabled_for_preset(batch.config.preset)
    extra_detectors = build_extra_detectors(ldap_enabled=ldap_enabled)

    # Policy hash
    batch.policy_hash = get_policy_hash(batch.config.preset)

    all_findings: List[Finding] = []
    global_warnings: List[str] = []
    _clear_parse_results(batch_id)

    for file_rec in batch.files:
        if file_rec.is_text_input:
            continue  # I file di testo inline sono gestiti da run_text_scan

        file_path = Path(file_rec.stored_path)
        logger.info("Processing file: %s", file_rec.original_name)

        # 1. Parsing
        parse_result = parse_file(file_path)
        _cache_parse_result(batch_id, file_rec.file_id, parse_result)

        if not parse_result.success:
            file_rec.status = FileStatus.FAILED
            file_rec.error_message = parse_result.error_message
            logger.warning("Parsing fallito per '%s': %s", file_rec.original_name, parse_result.error_message)
            continue

        file_rec.warnings.extend(parse_result.warnings)

        # 2. Detection
        raw_findings = detect_in_parse_result(parse_result, extra_detectors=extra_detectors)

        # 3. Pseudonimizzazione (usa engine persistente)
        file_findings = engine.process_findings(raw_findings, file_rec.file_id)

        # 4. Filtra per policy
        file_findings = _filter_findings_by_policy(file_findings, batch.config.preset)

        file_rec.findings_count = len(file_findings)
        all_findings.extend(file_findings)

        file_rec.status = FileStatus.PARSED
        logger.info("File '%s' processato: %d finding trovati.", file_rec.original_name, len(file_findings))

    # Mantieni i finding di testo inline già presenti
    existing_text_findings = [f for f in batch.findings if f.is_text_input]
    batch.findings = existing_text_findings + all_findings
    batch.status = BatchStatus.REVIEW
    update_batch(batch)

    logger.info(
        "Scansione completata per batch %s: %d finding totali in %d file.",
        batch_id, len(batch.findings), len(batch.files)
    )
    return batch


def apply_review_decisions(batch_id: str, decisions: List[ReviewDecisionItem]) -> Batch:
    """Applica le decisioni di review dell'utente ai finding del batch."""
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

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
    global_warnings: List[str] = []

    # Raggruppa i finding per file
    findings_by_file: Dict[str, List[Finding]] = {}
    for finding in batch.findings:
        if finding.file_id not in findings_by_file:
            findings_by_file[finding.file_id] = []
        findings_by_file[finding.file_id].append(finding)

    try:
        if not batch.config.is_dry_run:
            for file_rec in batch.files:
                if file_rec.status == FileStatus.FAILED or file_rec.is_text_input:
                    continue

                file_path = Path(file_rec.stored_path)
                file_findings = findings_by_file.get(file_rec.file_id, [])
                parse_result = _get_parse_result(batch_id, file_rec.file_id)

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

        completed_at = datetime.now(timezone.utc).isoformat()

        # Genera il mapping cifrato
        if passphrase and not batch.config.is_dry_run:
            mapping_data = {
                "batch_id": batch_id,
                "created_at": completed_at,
                "mode": batch.config.mode.value,
                "preset": batch.config.preset.value,
                "policy_hash": batch.policy_hash,
                "mapping": {}
            }
            for finding in batch.findings:
                if finding.review_action != ReviewAction.REJECT:
                    pseudo = finding.final_pseudonym
                    canon = finding.canonical_value or finding.original_value
                    if pseudo not in mapping_data["mapping"]:
                        mapping_data["mapping"][pseudo] = canon

            mapping_path = batch_dir / "mapping.enc"
            try:
                save_encrypted_mapping(mapping_data, passphrase, mapping_path)
            except Exception as e:
                logger.error("Errore nella cifratura del mapping: %s", e)

        # Calcola safety label
        residual_warnings = batch.residual_warnings or []
        safety = compute_safety_label(
            findings=batch.findings,
            file_records=batch.files,
            residual_warnings=residual_warnings,
            global_warnings=global_warnings,
        )
        batch.safety_label = safety

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
            if output_dir.exists():
                for output_file in output_dir.iterdir():
                    zf.write(str(output_file), f"files/{output_file.name}")
            if report_json_path.exists():
                zf.write(str(report_json_path), "report.json")
            if report_html_path.exists():
                zf.write(str(report_html_path), "report.html")
            mapping_path = batch_dir / "mapping.enc"
            if mapping_path.exists():
                zf.write(str(mapping_path), "mapping.enc")

        failed_files = [
            file_rec for file_rec in batch.files
            if not file_rec.is_text_input and file_rec.status == FileStatus.FAILED
        ]
        batch.status = BatchStatus.DONE_WITH_ERRORS if failed_files else BatchStatus.DONE
        update_batch(batch)

        logger.info("Pipeline completata per batch %s. ZIP: %s", batch_id, zip_path)
        return zip_path
    finally:
        _clear_parse_results(batch_id)
