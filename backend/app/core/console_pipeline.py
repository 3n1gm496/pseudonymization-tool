"""
Pipeline per testo inline (console/clipboard-first) v2.
Gestisce scan e apply su testo puro senza file fisici.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from app.core.batch_manager import get_batch, get_engine, get_or_create_engine, update_batch
from app.core.policies import get_confidence_threshold, get_enabled_entity_types
from app.core.safety import compute_residual_warnings, compute_safety_label
from app.detectors.engine import build_extra_detectors, detect_in_text, residual_scan
from app.models.schemas import (
    Batch,
    BatchStatus,
    EntityType,
    FileRecord,
    FileStatus,
    Finding,
    PresetName,
    ReviewAction,
    SafetyLabel,
)
from app.pseudonymizer.transformer import apply_pseudonyms_to_text

logger = logging.getLogger(__name__)


def run_text_scan(
    batch_id: str,
    text: str,
    label: str = "testo_incollato",
) -> tuple:
    """
    Esegue scan su testo inline e aggiunge i finding al batch.
    Restituisce (file_id, findings, safety_label).
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

    # Engine persistente del batch
    engine = get_or_create_engine(batch_id, batch.config.mode)

    # Extra detectors basati sulla policy
    from app.core.policies import is_ldap_enabled_for_preset

    ldap_enabled = is_ldap_enabled_for_preset(batch.config.preset)
    extra_detectors = build_extra_detectors(ldap_enabled=ldap_enabled)

    # Crea un FileRecord virtuale per il testo
    file_id = str(uuid.uuid4())
    file_rec = FileRecord(
        file_id=file_id,
        original_name=label,
        stored_path="",
        status=FileStatus.PARSED,
        is_text_input=True,
    )

    # Detection
    raw_findings = detect_in_text(text, extra_detectors=extra_detectors)

    # Pseudonimizzazione
    findings = engine.process_findings(raw_findings, file_id)

    # Filtra per policy
    enabled = set(get_enabled_entity_types(batch.config.preset))
    threshold = get_confidence_threshold(batch.config.preset)
    findings = [f for f in findings if f.entity_type.value in enabled and f.confidence_score >= threshold]

    # Marca i finding come testo inline
    for f in findings:
        f.is_text_input = True

    file_rec.findings_count = len(findings)

    # Calcola safety label per questa card
    safety = compute_safety_label(
        findings=findings,
        file_records=[file_rec],
        residual_warnings=[],
        global_warnings=[],
    )
    file_rec.safety_label = safety

    # Aggiorna il batch
    batch.files.append(file_rec)
    batch.findings.extend(findings)
    if batch.status == BatchStatus.PENDING:
        batch.status = BatchStatus.REVIEW
    update_batch(batch)

    logger.info("Text scan completato per batch %s, file_id=%s: %d finding", batch_id, file_id, len(findings))
    return file_id, findings, safety


def run_text_apply(
    batch_id: str,
    file_id: str,
    original_text: str,
) -> tuple:
    """
    Applica le sostituzioni al testo inline e restituisce il testo pseudonimizzato.
    Esegue anche il residual scan post-apply.
    Restituisce (pseudonymized_text, safety_label, residual_warnings, applied_count).
    """
    batch = get_batch(batch_id)
    if not batch:
        raise ValueError(f"Batch non trovato: {batch_id}")

    # Recupera i finding per questo file
    file_findings = [f for f in batch.findings if f.file_id == file_id]

    # Applica le sostituzioni
    pseudonymized_text, applied_count = apply_pseudonyms_to_text(original_text, file_findings)

    # Residual scan con whitelist dei valori sintetici (evita falsi positivi)
    extra_detectors = build_extra_detectors(ldap_enabled=False)
    # Costruisci la whitelist dai pseudonimi generati
    synthetic_whitelist = {
        f.proposed_pseudonym for f in file_findings if f.proposed_pseudonym and f.review_action != ReviewAction.REJECT
    }
    residual_raw = residual_scan(
        pseudonymized_text,
        extra_detectors=extra_detectors,
        synthetic_whitelist=synthetic_whitelist,
    )

    # Filtra residual per policy
    from app.core.policies import get_confidence_threshold, get_enabled_entity_types

    enabled = set(get_enabled_entity_types(batch.config.preset))
    threshold = get_confidence_threshold(batch.config.preset)
    residual_filtered = [r for r in residual_raw if r.entity_type.value in enabled and r.confidence_score >= threshold]

    residual_warnings = compute_residual_warnings(residual_filtered)

    # Aggiorna residual warnings nel batch
    batch.residual_warnings = list(set(batch.residual_warnings + residual_warnings))

    # Safety label
    file_rec = next((f for f in batch.files if f.file_id == file_id), None)
    safety = compute_safety_label(
        findings=file_findings,
        file_records=[file_rec] if file_rec else [],
        residual_warnings=residual_warnings,
        global_warnings=[],
    )
    if file_rec:
        file_rec.safety_label = safety
        file_rec.status = FileStatus.PROCESSED

    update_batch(batch)

    return pseudonymized_text, safety, residual_warnings, applied_count
