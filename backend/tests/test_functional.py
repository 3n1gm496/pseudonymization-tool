"""
Test funzionali completi per il Local Pseudonymization Tool.
Copertura: detector, parser, pseudonimizzatore, pipeline, cifratura, safety.

NOTA: Il precedente decorator @test custom catturava silenziosamente tutte le
eccezioni (incluse AssertionError) e le registrava come ERROR invece di
rilanciare, rendendo tutti i test falsi positivi per pytest.
Questo file è stato riscritto per usare pytest standard senza wrapper custom.
La funzione run_all_tests() è mantenuta per compatibilità con l'esecuzione
diretta via `python test_functional.py`.
"""

import json
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_DATA_DIR = Path(__file__).parent / "test_data"

# ─── Skip guard Tesseract ──────────────────────────────────────────────────────

pytesseract_available = pytest.mark.skipif(
    not shutil.which("tesseract"),
    reason="Tesseract OCR non installato — skip test immagine",
)


# ─── Helper ───────────────────────────────────────────────────────────────────


def _make_finding(original_value: str, entity_type_val: str, proposed_pseudonym: str):
    """Crea un Finding valido con tutti i campi obbligatori."""
    from app.models.schemas import EntityType, Finding

    return Finding(
        file_id="file-001",
        original_value=original_value,
        entity_type=EntityType(entity_type_val),
        proposed_pseudonym=proposed_pseudonym,
        confidence_score=0.95,
        detector_name="TEST_DETECTOR",
    )


# ─── Test Detector ────────────────────────────────────────────────────────────


def test_email_detection():
    from app.detectors.regex_detectors import EMAIL_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(
        text="Contatto: mario.rossi@ente.gov.it e luigi.ferrari@comune.it", source_ref="test.txt"
    )
    findings = detector.detect(chunk)
    values = [f.original_value for f in findings]
    assert "mario.rossi@ente.gov.it" in values, f"Email non trovata. Trovati: {values}"
    assert "luigi.ferrari@comune.it" in values, f"Email non trovata. Trovati: {values}"


def test_email_false_positives():
    from app.detectors.regex_detectors import EMAIL_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(text="Non è un'email: test@ oppure @esempio", source_ref="test.txt")
    findings = detector.detect(chunk)
    assert len(findings) == 0, f"Falsi positivi rilevati: {[f.original_value for f in findings]}"


def test_ipv4_detection():
    from app.detectors.regex_detectors import IPV4_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(text="Sorgente: 10.24.8.15, Destinazione: 192.168.1.100", source_ref="test.txt")
    findings = detector.detect(chunk)
    assert len(findings) == 2, f"Attesi 2, trovati {len(findings)}"


def test_ipv4_private_excluded():
    from app.detectors.regex_detectors import IPV4_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(text="Loopback: 127.0.0.1, Null: 0.0.0.0", source_ref="test.txt")
    findings = detector.detect(chunk)
    values = [f.original_value for f in findings]
    assert "127.0.0.1" not in values, "127.0.0.1 non deve essere rilevato"
    assert "0.0.0.0" not in values, "0.0.0.0 non deve essere rilevato"


def test_ipv6_detection():
    from app.detectors.regex_detectors import IPV6_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(
        text="Indirizzo: 2001:0db8:85a3:0000:0000:8a2e:0370:7334", source_ref="test.txt"
    )
    findings = detector.detect(chunk)
    assert len(findings) == 1, f"Atteso 1, trovato {len(findings)}"


def test_url_detection():
    from app.detectors.regex_detectors import URL_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(
        text="Accesso a https://intranet.ente.gov.it/admin e http://malicious.example.com/payload",
        source_ref="test.txt",
    )
    findings = detector.detect(chunk)
    assert len(findings) == 2, f"Attesi 2, trovati {len(findings)}"


def test_cf_detection():
    from app.detectors.regex_detectors import CODICE_FISCALE_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(text="CF: RSSMRA80A01H501A e FRRLGU75B12F205X", source_ref="test.txt")
    findings = detector.detect(chunk)
    assert len(findings) == 2, f"Attesi 2, trovati {len(findings)}"


def test_piva_detection():
    from app.detectors.regex_detectors import PARTITA_IVA_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(text="P.IVA: 12345678901 del fornitore", source_ref="test.txt")
    findings = detector.detect(chunk)
    assert len(findings) == 1, f"Atteso 1, trovato {len(findings)}"


def test_phone_detection():
    from app.detectors.regex_detectors import PHONE_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(text="Contatto: +39 333 1234567 oppure 06 1234 5678", source_ref="test.txt")
    findings = detector.detect(chunk)
    assert len(findings) >= 1, f"Atteso almeno 1, trovato {len(findings)}"


def test_hostname_detection():
    from app.detectors.regex_detectors import HOSTNAME_DETECTOR as detector
    from app.parsers.base import TextChunk

    chunk = TextChunk(
        text="Server: srv-dc-01.ente.local e srv-mail-01.ente.gov.it", source_ref="test.txt"
    )
    findings = detector.detect(chunk)
    assert len(findings) >= 1, f"Atteso almeno 1, trovato {len(findings)}"


def test_no_overlap_url_email():
    from app.detectors.engine import detect_in_chunk
    from app.parsers.base import TextChunk

    chunk = TextChunk(
        text="Accesso: https://intranet.ente.gov.it/admin da mario.rossi@ente.gov.it",
        source_ref="test.txt",
    )
    findings = detect_in_chunk(chunk)
    sorted_f = sorted(findings, key=lambda f: f.start_pos)
    for i in range(len(sorted_f) - 1):
        assert sorted_f[i].end_pos <= sorted_f[i + 1].start_pos, (
            f"Sovrapposizione tra '{sorted_f[i].original_value}' e '{sorted_f[i + 1].original_value}'"
        )


# ─── Test Parser ──────────────────────────────────────────────────────────────


def test_txt_parser():
    from app.parsers.text_parser import TextParser

    parser = TextParser()
    result = parser.parse(TEST_DATA_DIR / "test_log.txt")
    assert result.success, f"Parsing fallito: {result.error_message}"
    assert len(result.chunks) > 0, "Nessun chunk estratto"
    full_text = " ".join(c.text for c in result.chunks)
    assert "mario.rossi@ente.gov.it" in full_text


def test_csv_parser():
    from app.parsers.text_parser import TextParser

    parser = TextParser()
    result = parser.parse(TEST_DATA_DIR / "test_users.csv")
    assert result.success, f"Parsing fallito: {result.error_message}"
    full_text = " ".join(c.text for c in result.chunks)
    assert "mario.rossi@ente.gov.it" in full_text


def test_docx_parser():
    from app.parsers.docx_parser import DocxParser

    parser = DocxParser()
    result = parser.parse(TEST_DATA_DIR / "test_report.docx")
    assert result.success, f"Parsing fallito: {result.error_message}"
    full_text = " ".join(c.text for c in result.chunks)
    assert len(full_text) > 0, "Nessun testo estratto dal DOCX"


def test_xlsx_parser():
    from app.parsers.xlsx_parser import XlsxParser

    parser = XlsxParser()
    result = parser.parse(TEST_DATA_DIR / "test_data.xlsx")
    assert result.success, f"Parsing fallito: {result.error_message}"
    formula_chunks = [c for c in result.chunks if c.is_formula]
    assert len(formula_chunks) > 0, "Nessun chunk formula trovato nel file XLSX"
    full_text = " ".join(c.text for c in result.chunks if not c.is_formula)
    assert len(full_text) > 0, "Nessun testo estratto dall'XLSX"


def test_pdf_parser():
    from app.parsers.pdf_parser import PdfParser

    parser = PdfParser()
    result = parser.parse(TEST_DATA_DIR / "test_document.pdf")
    assert result.success, f"Parsing fallito: {result.error_message}"
    assert len(result.chunks) > 0, "Nessun chunk estratto dal PDF"


@pytesseract_available
def test_image_parser():
    from app.parsers.image_parser import ImageParser

    parser = ImageParser()
    result = parser.parse(TEST_DATA_DIR / "test_screenshot.png")
    assert result.success, (
        f"Parsing fallito: {result.error_message}. "
        "Verificare che Tesseract sia installato correttamente."
    )


@pytesseract_available
def test_jpg_exif_stripping():
    from app.parsers.image_parser import ImageParser

    parser = ImageParser()
    result = parser.parse(TEST_DATA_DIR / "test_screenshot_exif.jpg")
    assert result.success, (
        f"Parsing fallito: {result.error_message}. "
        "Verificare che Tesseract sia installato correttamente."
    )


def test_parser_factory():
    from app.parsers.docx_parser import DocxParser
    from app.parsers.factory import get_parser
    from app.parsers.image_parser import ImageParser
    from app.parsers.pdf_parser import PdfParser
    from app.parsers.text_parser import TextParser
    from app.parsers.xlsx_parser import XlsxParser

    assert isinstance(get_parser(Path("test.txt")), TextParser)
    assert isinstance(get_parser(Path("test.md")), TextParser)
    assert isinstance(get_parser(Path("test.csv")), TextParser)
    assert isinstance(get_parser(Path("test.docx")), DocxParser)
    assert isinstance(get_parser(Path("test.xlsx")), XlsxParser)
    assert isinstance(get_parser(Path("test.pdf")), PdfParser)
    assert isinstance(get_parser(Path("test.jpg")), ImageParser)
    assert isinstance(get_parser(Path("test.png")), ImageParser)


# ─── Test Safety Label (Critical Module) ──────────────────────────────────────


def test_safety_no_findings_no_warnings():
    """Nessun finding, nessun warning → SAFE_TO_UPLOAD."""
    from app.core.safety import compute_safety_label
    from app.models.schemas import SafetyLabel

    safety = compute_safety_label(
        findings=[], file_records=[], residual_warnings=[], global_warnings=[]
    )
    assert safety == SafetyLabel.SAFE_TO_UPLOAD, (
        f"Nessun finding/warning deve essere SAFE_TO_UPLOAD, got {safety}"
    )


def test_safety_global_warnings():
    """Global warnings → SAFE_WITH_WARNINGS."""
    from app.core.safety import compute_safety_label
    from app.models.schemas import SafetyLabel

    safety = compute_safety_label(
        findings=[],
        file_records=[],
        residual_warnings=[],
        global_warnings=["Dizionario LDAP non disponibile"],
    )
    assert safety == SafetyLabel.SAFE_WITH_WARNINGS, (
        f"Global warnings deve essere SAFE_WITH_WARNINGS, got {safety}"
    )


def test_safety_residual_warnings():
    """Residual warnings → SAFE_WITH_WARNINGS."""
    from app.core.safety import compute_safety_label
    from app.models.schemas import SafetyLabel

    safety = compute_safety_label(
        findings=[],
        file_records=[],
        residual_warnings=["Residual scan: trovati 2 potenziali finding"],
        global_warnings=[],
    )
    assert safety == SafetyLabel.SAFE_WITH_WARNINGS, (
        f"Residual warnings deve essere SAFE_WITH_WARNINGS, got {safety}"
    )


def test_safety_file_failed():
    """File con status FAILED → NOT_SAFE."""
    from app.core.safety import compute_safety_label
    from app.models.schemas import FileRecord, FileStatus, SafetyLabel

    file_rec = FileRecord(original_name="test.txt", stored_path="/tmp/test.txt")
    file_rec.status = FileStatus.FAILED
    file_rec.error_message = "Parsing error"

    safety = compute_safety_label(
        findings=[], file_records=[file_rec], residual_warnings=[], global_warnings=[]
    )
    assert safety == SafetyLabel.NOT_SAFE, (
        f"File FAILED deve essere NOT_SAFE, got {safety}"
    )


def test_safety_ocr_fail_warning():
    """Warning 'ocr fail' in file_record.warnings → NOT_SAFE."""
    from app.core.safety import compute_safety_label
    from app.models.schemas import FileRecord, FileStatus, SafetyLabel

    file_rec = FileRecord(original_name="scan.png", stored_path="/tmp/scan.png")
    file_rec.status = FileStatus.PROCESSED
    file_rec.warnings = ["ocr fail: impossibile leggere l'immagine"]

    safety = compute_safety_label(
        findings=[], file_records=[file_rec], residual_warnings=[], global_warnings=[]
    )
    assert safety == SafetyLabel.NOT_SAFE, (
        f"OCR fail deve essere NOT_SAFE, got {safety}"
    )


def test_safety_high_conf_rejected_above_threshold():
    """Più di 3 finding high-confidence (>=0.85) con REJECT → NOT_SAFE."""
    from app.core.safety import compute_safety_label
    from app.models.schemas import EntityType, Finding, ReviewAction, SafetyLabel

    findings = [
        Finding(
            file_id="file-001",
            original_value=f"user{i}@ente.gov.it",
            entity_type=EntityType.EMAIL,
            proposed_pseudonym=f"EMAIL_{i:03d}@pseudo.local",
            confidence_score=0.90,
            detector_name="EMAIL_DETECTOR",
            review_action=ReviewAction.REJECT,
        )
        for i in range(4)  # 4 > soglia 3
    ]

    safety = compute_safety_label(
        findings=findings, file_records=[], residual_warnings=[], global_warnings=[]
    )
    assert safety == SafetyLabel.NOT_SAFE, (
        f"4 high-conf REJECT deve essere NOT_SAFE, got {safety}"
    )


def test_safety_high_conf_rejected_at_threshold():
    """Esattamente 3 finding high-confidence con REJECT → SAFE_WITH_WARNINGS (non NOT_SAFE)."""
    from app.core.safety import compute_safety_label
    from app.models.schemas import EntityType, Finding, ReviewAction, SafetyLabel

    findings = [
        Finding(
            file_id="file-001",
            original_value=f"user{i}@ente.gov.it",
            entity_type=EntityType.EMAIL,
            proposed_pseudonym=f"EMAIL_{i:03d}@pseudo.local",
            confidence_score=0.90,
            detector_name="EMAIL_DETECTOR",
            review_action=ReviewAction.REJECT,
        )
        for i in range(3)  # 3 == soglia, non supera
    ]

    safety = compute_safety_label(
        findings=findings, file_records=[], residual_warnings=[], global_warnings=[]
    )
    assert safety == SafetyLabel.SAFE_WITH_WARNINGS, (
        f"3 high-conf REJECT deve essere SAFE_WITH_WARNINGS, got {safety}"
    )


def test_safety_compute_residual_warnings_empty():
    """Nessun finding residuo → lista vuota."""
    from app.core.safety import compute_residual_warnings

    warnings = compute_residual_warnings([])
    assert warnings == [], f"Lista vuota attesa, got {warnings}"


def test_safety_compute_residual_warnings_with_findings():
    """Finding residui → warnings con conteggio totale e per tipo."""
    from app.core.safety import compute_residual_warnings
    from app.models.schemas import EntityType, Finding

    findings = [
        Finding(
            file_id="file-001",
            original_value="mario.rossi@ente.gov.it",
            entity_type=EntityType.EMAIL,
            proposed_pseudonym="EMAIL_001@pseudo.local",
            confidence_score=0.95,
            detector_name="EMAIL_DETECTOR",
        ),
        Finding(
            file_id="file-001",
            original_value="10.24.8.15",
            entity_type=EntityType.IPV4,
            proposed_pseudonym="10.0.0.1",
            confidence_score=0.99,
            detector_name="IPV4_DETECTOR",
        ),
    ]

    warnings = compute_residual_warnings(findings)
    assert len(warnings) >= 1, "Almeno un warning atteso"
    # Il primo warning deve contenere il conteggio totale (2)
    assert any("2" in w for w in warnings), f"Conteggio totale mancante: {warnings}"


# ─── Test Pipeline Critical ────────────────────────────────────────────────────


def test_pipeline_parsing_nonexistent_file():
    """Parsing di file inesistente → result.success = False."""
    from app.parsers.factory import parse_file

    result = parse_file(Path("/nonexistent/file.txt"))
    assert not result.success, "Parsing di file inesistente deve fallire con success=False"


def test_pipeline_batch_not_found():
    """Batch inesistente → BatchStateError con batch_id nel messaggio."""
    from app.core.exceptions import BatchStateError
    from app.core.pipeline import run_scan_pipeline

    with pytest.raises(BatchStateError) as exc_info:
        run_scan_pipeline("nonexistent-batch-id")
    assert "nonexistent-batch-id" in str(exc_info.value)


# ─── Test Transformer — Review Actions ────────────────────────────────────────


def test_transformer_action_accept():
    """ReviewAction.ACCEPT → final_pseudonym = proposed_pseudonym."""
    from app.models.schemas import ReviewAction

    finding = _make_finding("mario.rossi@ente.gov.it", "EMAIL", "EMAIL_001@pseudo.local")
    finding.review_action = ReviewAction.ACCEPT
    assert finding.final_pseudonym == "EMAIL_001@pseudo.local", (
        f"ACCEPT deve usare proposed_pseudonym, got '{finding.final_pseudonym}'"
    )


def test_transformer_action_modify():
    """ReviewAction.MODIFY con modified_pseudonym → final_pseudonym = modified_pseudonym."""
    from app.models.schemas import ReviewAction

    finding = _make_finding("mario.rossi@ente.gov.it", "EMAIL", "EMAIL_001@pseudo.local")
    finding.review_action = ReviewAction.MODIFY
    finding.modified_pseudonym = "m.rossi@redacted.local"
    assert finding.final_pseudonym == "m.rossi@redacted.local", (
        f"MODIFY deve usare modified_pseudonym, got '{finding.final_pseudonym}'"
    )


def test_transformer_action_reject():
    """ReviewAction.REJECT → final_pseudonym = original_value (non sostituire)."""
    from app.models.schemas import ReviewAction

    finding = _make_finding("mario.rossi@ente.gov.it", "EMAIL", "EMAIL_001@pseudo.local")
    finding.review_action = ReviewAction.REJECT
    assert finding.final_pseudonym == "mario.rossi@ente.gov.it", (
        f"REJECT deve restituire original_value, got '{finding.final_pseudonym}'"
    )


def test_transformer_action_modify_without_modified_pseudonym():
    """ReviewAction.MODIFY senza modified_pseudonym → fallback a proposed_pseudonym."""
    from app.models.schemas import ReviewAction

    finding = _make_finding("mario.rossi@ente.gov.it", "EMAIL", "EMAIL_001@pseudo.local")
    finding.review_action = ReviewAction.MODIFY
    finding.modified_pseudonym = None
    # Senza modified_pseudonym, deve usare proposed_pseudonym come fallback
    assert finding.final_pseudonym == "EMAIL_001@pseudo.local", (
        f"MODIFY senza modified_pseudonym deve usare proposed_pseudonym, got '{finding.final_pseudonym}'"
    )


# ─── Test Pseudonimizzatore ────────────────────────────────────────────────────


def test_pseudonym_consistency():
    """Stesso valore → stesso pseudonimo (idempotenza)."""
    from app.models.schemas import BatchMode, EntityType
    from app.pseudonymizer.engine import PseudonymEngine

    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    p1 = engine.get_or_create_pseudonym(EntityType.EMAIL, "mario.rossi@ente.gov.it")
    p2 = engine.get_or_create_pseudonym(EntityType.EMAIL, "mario.rossi@ente.gov.it")
    assert p1 == p2, f"Stesso valore deve produrre stesso pseudonimo: '{p1}' != '{p2}'"


def test_pseudonym_uniqueness():
    """Valori diversi → pseudonimi diversi."""
    from app.models.schemas import BatchMode, EntityType
    from app.pseudonymizer.engine import PseudonymEngine

    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    p1 = engine.get_or_create_pseudonym(EntityType.EMAIL, "mario.rossi@ente.gov.it")
    p2 = engine.get_or_create_pseudonym(EntityType.EMAIL, "luigi.ferrari@ente.gov.it")
    assert p1 != p2, f"Valori diversi devono produrre pseudonimi diversi: '{p1}' == '{p2}'"


def test_pseudonym_light_email_format():
    """Light mode: pseudonimo email deve contenere @."""
    from app.models.schemas import BatchMode, EntityType
    from app.pseudonymizer.engine import PseudonymEngine

    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    p = engine.get_or_create_pseudonym(EntityType.EMAIL, "mario.rossi@ente.gov.it")
    assert "@" in p, f"Pseudonimo email deve contenere @: {p}"


def test_pseudonym_strict_no_original():
    """Strict mode: pseudonimo non deve contenere il nome originale."""
    from app.models.schemas import BatchMode, EntityType
    from app.pseudonymizer.engine import PseudonymEngine

    engine = PseudonymEngine(mode=BatchMode.STRICT)
    p = engine.get_or_create_pseudonym(EntityType.EMAIL, "mario.rossi@ente.gov.it")
    assert "mario.rossi" not in p, f"Pseudonimo Strict non deve contenere il nome originale: {p}"


def test_pseudonym_light_ipv4_structure():
    """IPv4 Light mode: struttura preservata (primi ottetti)."""
    from app.models.schemas import BatchMode, EntityType
    from app.pseudonymizer.engine import PseudonymEngine

    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    p = engine.get_or_create_pseudonym(EntityType.IPV4, "10.24.8.15")
    assert "10.24" in p, f"IPv4 Light deve preservare i primi ottetti: {p}"


# ─── Test Cifratura Mapping ────────────────────────────────────────────────────


def test_crypto_roundtrip():
    """Encrypt/Decrypt round-trip corretto."""
    from app.mapping.crypto import decrypt_mapping, encrypt_mapping

    data = {"batch_id": "test-123", "mapping": {"EMAIL_001": "mario.rossi@ente.gov.it"}}
    passphrase = "TestPassphrase2024!"
    encrypted = encrypt_mapping(data, passphrase)
    decrypted = decrypt_mapping(encrypted, passphrase)
    assert decrypted["batch_id"] == data["batch_id"]
    assert decrypted["mapping"] == data["mapping"]


def test_crypto_wrong_passphrase():
    """Passphrase errata → InvalidTag."""
    from app.mapping.crypto import decrypt_mapping, encrypt_mapping
    from cryptography.exceptions import InvalidTag

    data = {"test": "value"}
    encrypted = encrypt_mapping(data, "CorrectPassphrase")
    with pytest.raises(InvalidTag):
        decrypt_mapping(encrypted, "WrongPassphrase")


def test_crypto_random_salt():
    """Output cifrato diverso ad ogni chiamata (salt casuale)."""
    from app.mapping.crypto import encrypt_mapping

    data = {"test": "value"}
    enc1 = encrypt_mapping(data, "SamePassphrase")
    enc2 = encrypt_mapping(data, "SamePassphrase")
    assert enc1 != enc2, "Ogni cifratura deve produrre output diverso (salt casuale)"


def test_crypto_file_save_load():
    """File di mapping salvato e riletto correttamente."""
    from app.mapping.crypto import load_and_decrypt_mapping, save_encrypted_mapping

    data = {"batch_id": "test-456", "mapping": {"IPV4_001": "10.24.8.15"}}
    with tempfile.NamedTemporaryFile(suffix=".enc", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        save_encrypted_mapping(data, "TestPw123!", tmp_path)
        loaded = load_and_decrypt_mapping(tmp_path, "TestPw123!")
        assert loaded["batch_id"] == data["batch_id"]
    finally:
        tmp_path.unlink(missing_ok=True)


# ─── Test Pipeline End-to-End ──────────────────────────────────────────────────


def test_pipeline_e2e_txt():
    """Pipeline E2E: TXT — detection e pseudonimizzazione."""
    from app.detectors.engine import detect_in_parse_result
    from app.models.schemas import BatchMode
    from app.parsers.factory import parse_file
    from app.pseudonymizer.engine import PseudonymEngine

    result = parse_file(TEST_DATA_DIR / "test_log.txt")
    assert result.success
    raw_findings = detect_in_parse_result(result)
    assert len(raw_findings) > 0, "Nessun finding nel file TXT di test"
    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    findings = engine.process_findings(raw_findings, "file-001")
    assert len(findings) == len(raw_findings)
    types = {f.entity_type.value for f in findings}
    assert "EMAIL" in types, f"Email non trovata. Tipi trovati: {types}"
    assert "IPV4" in types, f"IPv4 non trovato. Tipi trovati: {types}"


def test_pipeline_e2e_csv():
    """Pipeline E2E: CSV — detection corretta."""
    from app.detectors.engine import detect_in_parse_result
    from app.models.schemas import BatchMode
    from app.parsers.factory import parse_file
    from app.pseudonymizer.engine import PseudonymEngine

    result = parse_file(TEST_DATA_DIR / "test_users.csv")
    assert result.success
    raw_findings = detect_in_parse_result(result)
    assert len(raw_findings) > 0
    engine = PseudonymEngine(mode=BatchMode.STRICT)
    findings = engine.process_findings(raw_findings, "file-002")
    types = {f.entity_type.value for f in findings}
    assert "EMAIL" in types
    assert "CODICE_FISCALE" in types


def test_pipeline_e2e_xlsx_formulas():
    """Pipeline E2E: XLSX — formule non processate dai detector."""
    from app.detectors.engine import detect_in_chunk
    from app.parsers.factory import parse_file

    result = parse_file(TEST_DATA_DIR / "test_data.xlsx")
    assert result.success
    formula_chunks = [c for c in result.chunks if c.is_formula]
    assert len(formula_chunks) > 0, "Nessun chunk formula trovato nel file XLSX"
    for chunk in formula_chunks:
        findings = detect_in_chunk(chunk)
        assert len(findings) == 0, f"Finding in chunk formula: {chunk.text}"


def test_transformer_txt_no_originals():
    """Transformer: TXT — valori originali non presenti nel testo trasformato."""
    from app.detectors.engine import detect_in_parse_result
    from app.models.schemas import BatchMode, ReviewAction
    from app.parsers.factory import parse_file
    from app.pseudonymizer.engine import PseudonymEngine
    from app.pseudonymizer.transformer import apply_pseudonyms_to_text

    result = parse_file(TEST_DATA_DIR / "test_log.txt")
    raw_findings = detect_in_parse_result(result)
    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    findings = engine.process_findings(raw_findings, "file-001")
    # Accetta tutti i finding per la sostituzione
    for f in findings:
        f.review_action = ReviewAction.ACCEPT
    full_text = " ".join(c.text for c in result.chunks)
    transformed_text, n_applied = apply_pseudonyms_to_text(full_text, findings)
    assert n_applied > 0, "Nessuna sostituzione applicata"
    assert "mario.rossi@ente.gov.it" not in transformed_text, (
        "Il valore originale non deve essere nel testo trasformato"
    )


def test_report_json_structure():
    """Report JSON: struttura attesa e nessun valore originale."""
    from app.detectors.engine import detect_in_parse_result
    from app.models.schemas import Batch, BatchConfig, BatchMode, FileRecord, FileStatus
    from app.parsers.factory import parse_file
    from app.pseudonymizer.engine import PseudonymEngine
    from app.report.generator import build_report_data, generate_json_report

    result = parse_file(TEST_DATA_DIR / "test_log.txt")
    raw_findings = detect_in_parse_result(result)
    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    findings = engine.process_findings(raw_findings, "file-001")
    config = BatchConfig(mode=BatchMode.LIGHT)
    batch = Batch(config=config)
    file_rec = FileRecord(
        original_name="test_log.txt", stored_path=str(TEST_DATA_DIR / "test_log.txt")
    )
    file_rec.status = FileStatus.PROCESSED
    file_rec.findings_count = len(findings)
    batch.files.append(file_rec)
    batch.findings = findings
    report_data = build_report_data(batch, findings, "2024-03-15T09:00:00", "2024-03-15T09:01:00")
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "report.json"
        generate_json_report(report_data, report_path)
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert "batch_id" in data, "Campo batch_id mancante nel report"
        assert "summary" in data, "Campo summary mancante nel report"
        assert "findings_by_type" in data, "Campo findings_by_type mancante nel report"
        report_str = report_path.read_text()
        assert "mario.rossi@ente.gov.it" not in report_str, (
            "I valori originali non devono essere nel report JSON"
        )


# ─── Test Sicurezza ────────────────────────────────────────────────────────────


def test_security_no_originals_in_report():
    """Nessun valore sensibile nel report JSON."""
    from app.detectors.engine import detect_in_parse_result
    from app.models.schemas import Batch, BatchConfig, BatchMode, FileRecord, FileStatus
    from app.parsers.factory import parse_file
    from app.pseudonymizer.engine import PseudonymEngine
    from app.report.generator import build_report_data

    result = parse_file(TEST_DATA_DIR / "test_users.csv")
    raw_findings = detect_in_parse_result(result)
    engine = PseudonymEngine(mode=BatchMode.STRICT)
    findings = engine.process_findings(raw_findings, "file-001")
    config = BatchConfig(mode=BatchMode.STRICT)
    batch = Batch(config=config)
    file_rec = FileRecord(
        original_name="test_users.csv", stored_path=str(TEST_DATA_DIR / "test_users.csv")
    )
    file_rec.status = FileStatus.PROCESSED
    batch.files.append(file_rec)
    report_data = build_report_data(batch, findings, "2024-03-15T09:00:00", "2024-03-15T09:01:00")
    report_str = json.dumps(report_data)
    sensitive_values = ["mario.rossi@ente.gov.it", "RSSMRA80A01H501A", "10.24.1.15"]
    for val in sensitive_values:
        assert val not in report_str, f"Valore sensibile trovato nel report: {val}"


def test_security_mapping_encrypted():
    """Mapping cifrato: valore originale non leggibile, passphrase errata → InvalidTag."""
    from app.mapping.crypto import load_and_decrypt_mapping, save_encrypted_mapping
    from cryptography.exceptions import InvalidTag

    data = {"mapping": {"EMAIL_001": "mario.rossi@ente.gov.it"}}
    with tempfile.NamedTemporaryFile(suffix=".enc", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        save_encrypted_mapping(data, "SecurePassphrase2024!", tmp_path)
        raw_bytes = tmp_path.read_bytes()
        assert b"mario.rossi" not in raw_bytes, "Valore originale leggibile in chiaro nel file cifrato"
        with pytest.raises(InvalidTag):
            load_and_decrypt_mapping(tmp_path, "WrongPassword")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_security_no_sensitive_in_logs():
    """Detector non espone valori originali nei log."""
    import io
    import logging

    from app.detectors.engine import detect_in_chunk
    from app.parsers.base import TextChunk

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logging.getLogger("app").addHandler(handler)
    try:
        chunk = TextChunk(
            text="Email: mario.rossi@ente.gov.it, CF: RSSMRA80A01H501A", source_ref="sec-test"
        )
        detect_in_chunk(chunk)
    finally:
        logging.getLogger("app").removeHandler(handler)

    log_output = log_capture.getvalue()
    assert "mario.rossi@ente.gov.it" not in log_output, "Email sensibile nei log"
    assert "RSSMRA80A01H501A" not in log_output, "CF sensibile nei log"


# ─── Esecuzione standalone ─────────────────────────────────────────────────────


def _run_standalone(name: str, fn) -> dict:
    """Esegue un test e restituisce il risultato per run_all_tests()."""
    start = time.time()
    try:
        fn()
        elapsed = time.time() - start
        result = {"name": name, "status": "PASS", "elapsed": round(elapsed, 3), "error": None}
        print(f"  ✓ PASS  {name}  ({elapsed:.3f}s)")
    except AssertionError as e:
        elapsed = time.time() - start
        result = {"name": name, "status": "FAIL", "elapsed": round(elapsed, 3), "error": str(e)}
        print(f"  ✗ FAIL  {name}: {e}")
    except Exception as e:
        elapsed = time.time() - start
        result = {"name": name, "status": "ERROR", "elapsed": round(elapsed, 3), "error": str(e)}
        print(f"  ! ERR   {name}: {e}")
        traceback.print_exc()
    return result


def run_all_tests():
    """
    Esecuzione standalone di tutti i test funzionali.
    Usare pytest per l'esecuzione in CI — questa funzione è mantenuta
    per compatibilità con `python test_functional.py`.
    """
    test_fns = [
        ("Detector: Email valide", test_email_detection),
        ("Detector: Email falsi positivi", test_email_false_positives),
        ("Detector: IPv4", test_ipv4_detection),
        ("Detector: IPv4 privati esclusi", test_ipv4_private_excluded),
        ("Detector: IPv6", test_ipv6_detection),
        ("Detector: URL", test_url_detection),
        ("Detector: Codice Fiscale", test_cf_detection),
        ("Detector: Partita IVA", test_piva_detection),
        ("Detector: Telefono", test_phone_detection),
        ("Detector: Hostname", test_hostname_detection),
        ("Detector: No overlap URL/Email", test_no_overlap_url_email),
        ("Parser: TXT", test_txt_parser),
        ("Parser: CSV", test_csv_parser),
        ("Parser: DOCX", test_docx_parser),
        ("Parser: XLSX", test_xlsx_parser),
        ("Parser: PDF", test_pdf_parser),
        ("Parser: Factory", test_parser_factory),
        ("Safety: No findings = SAFE_TO_UPLOAD", test_safety_no_findings_no_warnings),
        ("Safety: Global warnings = SAFE_WITH_WARNINGS", test_safety_global_warnings),
        ("Safety: Residual warnings = SAFE_WITH_WARNINGS", test_safety_residual_warnings),
        ("Safety: File FAILED = NOT_SAFE", test_safety_file_failed),
        ("Safety: OCR fail = NOT_SAFE", test_safety_ocr_fail_warning),
        ("Safety: >3 high-conf REJECT = NOT_SAFE", test_safety_high_conf_rejected_above_threshold),
        ("Safety: <=3 high-conf REJECT = SAFE_WITH_WARNINGS", test_safety_high_conf_rejected_at_threshold),
        ("Safety: compute_residual_warnings vuoto", test_safety_compute_residual_warnings_empty),
        ("Safety: compute_residual_warnings con findings", test_safety_compute_residual_warnings_with_findings),
        ("Pipeline: File inesistente = success=False", test_pipeline_parsing_nonexistent_file),
        ("Pipeline: BatchStateError batch non trovato", test_pipeline_batch_not_found),
        ("Transformer: ACCEPT", test_transformer_action_accept),
        ("Transformer: MODIFY", test_transformer_action_modify),
        ("Transformer: REJECT", test_transformer_action_reject),
        ("Transformer: MODIFY senza modified_pseudonym", test_transformer_action_modify_without_modified_pseudonym),
        ("Pseudonimizzatore: Consistenza", test_pseudonym_consistency),
        ("Pseudonimizzatore: Unicità", test_pseudonym_uniqueness),
        ("Pseudonimizzatore: Light email format", test_pseudonym_light_email_format),
        ("Pseudonimizzatore: Strict no original", test_pseudonym_strict_no_original),
        ("Pseudonimizzatore: IPv4 Light struttura", test_pseudonym_light_ipv4_structure),
        ("Cifratura: Round-trip", test_crypto_roundtrip),
        ("Cifratura: Passphrase errata", test_crypto_wrong_passphrase),
        ("Cifratura: Salt casuale", test_crypto_random_salt),
        ("Cifratura: File save/load", test_crypto_file_save_load),
        ("Pipeline E2E: TXT", test_pipeline_e2e_txt),
        ("Pipeline E2E: CSV", test_pipeline_e2e_csv),
        ("Pipeline E2E: XLSX formule", test_pipeline_e2e_xlsx_formulas),
        ("Transformer: TXT no originals", test_transformer_txt_no_originals),
        ("Report: JSON struttura", test_report_json_structure),
        ("Sicurezza: No originali nel report", test_security_no_originals_in_report),
        ("Sicurezza: Mapping cifrato", test_security_mapping_encrypted),
        ("Sicurezza: No sensibili nei log", test_security_no_sensitive_in_logs),
    ]

    print(f"\n{'=' * 60}")
    print("Local Pseudonymization Tool — Test Suite")
    print(f"Esecuzione: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    results = [_run_standalone(name, fn) for name, fn in test_fns]

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    total = len(results)

    print(f"\n{'=' * 60}")
    print(f"RISULTATI: {passed}/{total} PASS | {failed} FAIL | {errors} ERROR")
    print(f"{'=' * 60}")

    if failed > 0 or errors > 0:
        print("\nTest falliti/errori:")
        for r in results:
            if r["status"] != "PASS":
                print(f"  [{r['status']}] {r['name']}: {r['error']}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {"total": total, "passed": passed, "failed": failed, "errors": errors},
        "results": results,
    }
    report_path = Path(__file__).parent / "test_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport salvato in: {report_path}")

    return failed == 0 and errors == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
