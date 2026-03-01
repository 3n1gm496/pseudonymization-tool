"""
Calcolo del SafetyLabel per batch e card.
SAFE_TO_UPLOAD / SAFE_WITH_WARNINGS / NOT_SAFE
Il label è solo informativo e non blocca copy/export.
"""

from typing import List

from app.models.schemas import FileRecord, FileStatus, Finding, ReviewAction, SafetyLabel


def compute_safety_label(
    findings: List[Finding],
    file_records: List[FileRecord],
    residual_warnings: List[str],
    global_warnings: List[str],
) -> SafetyLabel:
    """
    Calcola il SafetyLabel per un batch o una card.

    NOT_SAFE se:
    - Ci sono file non processabili (FAILED) o con OCR fallito
    - Ci sono finding high-confidence esclusi dall'utente (review_action=REJECT)

    SAFE_WITH_WARNINGS se:
    - OCR parziale (warning nei file record)
    - Residual findings high/medium dopo apply
    - Finding high-confidence esclusi (REJECT) ma non critici

    SAFE_TO_UPLOAD se:
    - Nessun warning critico
    - Residual scan pulito
    """
    # NOT_SAFE: file failed o OCR completamente fallito
    for fr in file_records:
        if fr.status == FileStatus.FAILED:
            return SafetyLabel.NOT_SAFE
        for w in fr.warnings:
            if "ocr" in w.lower() and "fail" in w.lower():
                return SafetyLabel.NOT_SAFE

    # NOT_SAFE: finding high-confidence con REJECT (utente ha escluso entità critiche)
    high_conf_rejected = [f for f in findings if f.review_action == ReviewAction.REJECT and f.confidence_score >= 0.85]
    if len(high_conf_rejected) > 3:  # Soglia: più di 3 entità critiche escluse
        return SafetyLabel.NOT_SAFE

    # SAFE_WITH_WARNINGS: residual findings
    if residual_warnings:
        return SafetyLabel.SAFE_WITH_WARNINGS

    # SAFE_WITH_WARNINGS: OCR parziale
    for fr in file_records:
        for w in fr.warnings:
            if "ocr" in w.lower() or "parzial" in w.lower():
                return SafetyLabel.SAFE_WITH_WARNINGS

    # SAFE_WITH_WARNINGS: global warnings
    if global_warnings:
        return SafetyLabel.SAFE_WITH_WARNINGS

    # SAFE_WITH_WARNINGS: alcuni finding esclusi
    if high_conf_rejected:
        return SafetyLabel.SAFE_WITH_WARNINGS

    return SafetyLabel.SAFE_TO_UPLOAD


def compute_residual_warnings(residual_findings: List) -> List[str]:
    """
    Genera i warning per i finding residui dopo apply.
    """
    if not residual_findings:
        return []

    warnings = []
    by_type: dict = {}
    for f in residual_findings:
        t = f.entity_type.value if hasattr(f.entity_type, "value") else str(f.entity_type)
        by_type[t] = by_type.get(t, 0) + 1

    total = len(residual_findings)
    warnings.append(
        f"Residual scan: trovati {total} potenziali finding nel testo pseudonimizzato. "
        f"Verificare manualmente prima di condividere."
    )
    for t, count in by_type.items():
        warnings.append(f"  - {t}: {count} occorrenza/e residua/e")

    return warnings
