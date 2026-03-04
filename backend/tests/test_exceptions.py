"""
Tests for app.core.exceptions — targeting 100% coverage.

Each test instantiates the exception class directly and verifies:
- The string representation contains the expected substrings
- Custom attributes (filename, batch_id, operation, component, ...) are set
- Inheritance chain is correct (RecoverableError vs CriticalError)
- Helper functions exception_to_http_status and exception_to_detail behave correctly
"""

import pytest
from app.core.exceptions import (
    ApplyPipelineError,
    BatchAlreadyExistsError,
    BatchCleanupError,
    BatchError,
    BatchNotFoundError,
    BatchStateError,
    BatchStorageError,
    ConfigError,
    CriticalError,
    CryptoError,
    DecryptionError,
    DetectionError,
    DictionaryLoadError,
    DocxParsingError,
    EncryptionError,
    FileEncodingError,
    ImageParsingError,
    InvalidPassphraseError,
    LDAPDetectionError,
    MalformedFileError,
    MappingFileError,
    ParsingError,
    PDFParsingError,
    PipelineError,
    PolicyError,
    PolicyLoadError,
    PseudonymizationError,
    RecoverableError,
    SafetyCheckError,
    ScanPipelineError,
    TransformError,
    UnsupportedFormatError,
    exception_to_detail,
    exception_to_http_status,
)

# ─── Base exceptions ──────────────────────────────────────────────────────────


def test_pseudonymization_error_is_exception():
    exc = PseudonymizationError("base error")
    assert isinstance(exc, Exception)
    assert str(exc) == "base error"


def test_recoverable_error_inherits_pseudonymization_error():
    exc = RecoverableError("recoverable")
    assert isinstance(exc, PseudonymizationError)


def test_critical_error_inherits_pseudonymization_error():
    exc = CriticalError("critical")
    assert isinstance(exc, PseudonymizationError)


# ─── Parsing exceptions ───────────────────────────────────────────────────────


def test_parsing_error_attributes():
    exc = ParsingError("file.txt", "text", "bad encoding")
    assert exc.filename == "file.txt"
    assert exc.format_type == "text"
    assert exc.reason == "bad encoding"
    assert "file.txt" in str(exc)
    assert "bad encoding" in str(exc)
    assert isinstance(exc, RecoverableError)


def test_unsupported_format_error():
    exc = UnsupportedFormatError("file.xyz", ".xyz")
    assert exc.filename == "file.xyz"
    assert ".xyz" in str(exc)
    assert isinstance(exc, ParsingError)


def test_malformed_file_error():
    exc = MalformedFileError("data.csv", "CSV", "missing header")
    assert exc.filename == "data.csv"
    assert "missing header" in str(exc)
    assert isinstance(exc, ParsingError)


def test_file_encoding_error():
    exc = FileEncodingError("file.txt", "latin-1")
    assert exc.filename == "file.txt"
    assert "latin-1" in str(exc)
    assert isinstance(exc, ParsingError)


def test_pdf_parsing_error():
    exc = PDFParsingError("doc.pdf", "corrupted stream")
    assert exc.filename == "doc.pdf"
    assert "corrupted stream" in str(exc)
    assert isinstance(exc, ParsingError)


def test_docx_parsing_error():
    exc = DocxParsingError("report.docx", "missing content.xml")
    assert exc.filename == "report.docx"
    assert "missing content.xml" in str(exc)
    assert isinstance(exc, ParsingError)


def test_xlsx_parsing_error():
    from app.core.exceptions import XlsxParsingError

    exc = XlsxParsingError("data.xlsx", "sheet not found")
    assert exc.filename == "data.xlsx"
    assert "sheet not found" in str(exc)
    assert isinstance(exc, ParsingError)


def test_image_parsing_error():
    exc = ImageParsingError("photo.png", "OCR failed")
    assert exc.filename == "photo.png"
    assert "OCR failed" in str(exc)
    assert isinstance(exc, ParsingError)


# ─── Detection exceptions ─────────────────────────────────────────────────────


def test_detection_error_attributes():
    exc = DetectionError("NER", "model not loaded")
    assert exc.detector_type == "NER"
    assert exc.reason == "model not loaded"
    assert "NER" in str(exc)
    assert isinstance(exc, RecoverableError)


def test_regex_detection_error():
    from app.core.exceptions import RegexDetectionError

    exc = RegexDetectionError("email_pattern", "invalid regex")
    assert "email_pattern" in str(exc)
    assert "invalid regex" in str(exc)
    assert isinstance(exc, DetectionError)


def test_dictionary_detection_error():
    from app.core.exceptions import DictionaryDetectionError

    exc = DictionaryDetectionError("dict file missing")
    assert "dictionary" in str(exc)
    assert "dict file missing" in str(exc)
    assert isinstance(exc, DetectionError)


def test_ldap_detection_error():
    from app.core.exceptions import LDAPDetectionError

    exc = LDAPDetectionError("server unreachable")
    assert "ldap" in str(exc)
    assert isinstance(exc, DetectionError)


def test_ldap_connection_error():
    from app.core.exceptions import LDAPConnectionError

    exc = LDAPConnectionError("ldap.example.com", 389, "timeout")
    assert exc.host == "ldap.example.com"
    assert exc.port == 389
    assert "timeout" in str(exc)
    assert isinstance(exc, LDAPDetectionError)


def test_ldap_auth_error():
    from app.core.exceptions import LDAPAuthError

    exc = LDAPAuthError("invalid credentials")
    assert "invalid credentials" in str(exc)
    assert isinstance(exc, LDAPDetectionError)


def test_ldap_paging_error():
    from app.core.exceptions import LDAPPagingError

    exc = LDAPPagingError("page size exceeded")
    assert "page size exceeded" in str(exc)
    assert isinstance(exc, LDAPDetectionError)


# ─── Transform exceptions ─────────────────────────────────────────────────────


def test_transform_error_attributes():
    exc = TransformError("file.txt", "text", "engine error")
    assert exc.filename == "file.txt"
    assert exc.format_type == "text"
    assert exc.reason == "engine error"
    assert "engine error" in str(exc)
    assert isinstance(exc, RecoverableError)


def test_pseudonymization_transform_error():
    from app.core.exceptions import PseudonymizationTransformError

    exc = PseudonymizationTransformError("file.txt", "text", 5, "mapping missing")
    assert exc.entity_count == 5
    assert "5" in str(exc)
    assert isinstance(exc, TransformError)


def test_pdf_transform_error():
    from app.core.exceptions import PDFTransformError

    exc = PDFTransformError("doc.pdf", "rendering failed")
    assert exc.filename == "doc.pdf"
    assert "rendering failed" in str(exc)
    assert isinstance(exc, TransformError)


def test_docx_transform_error():
    from app.core.exceptions import DocxTransformError

    exc = DocxTransformError("report.docx", "xml error")
    assert exc.filename == "report.docx"
    assert "xml error" in str(exc)
    assert isinstance(exc, TransformError)


def test_xlsx_transform_error():
    from app.core.exceptions import XlsxTransformError

    exc = XlsxTransformError("data.xlsx", "sheet locked")
    assert exc.filename == "data.xlsx"
    assert "sheet locked" in str(exc)
    assert isinstance(exc, TransformError)


def test_image_transform_error():
    from app.core.exceptions import ImageTransformError

    exc = ImageTransformError("photo.png", "overlay failed")
    assert exc.filename == "photo.png"
    assert "overlay failed" in str(exc)
    assert isinstance(exc, TransformError)


# ─── Policy exceptions ────────────────────────────────────────────────────────


def test_policy_error_attributes():
    exc = PolicyError("GDPR", "missing consent field")
    assert exc.policy_name == "GDPR"
    assert "missing consent field" in str(exc)
    assert isinstance(exc, RecoverableError)


def test_safety_check_error():
    exc = SafetyCheckError("PERSON", "confidence too low")
    assert exc.entity_type == "PERSON"
    assert "confidence too low" in str(exc)
    assert isinstance(exc, RecoverableError)


def test_invalid_policy_error():
    from app.core.exceptions import InvalidPolicyError

    exc = InvalidPolicyError("GDPR", "min_confidence", "must be between 0 and 1")
    assert exc.policy_name == "GDPR"
    assert "min_confidence" in str(exc)
    assert isinstance(exc, PolicyError)


def test_confidence_threshold_error():
    from app.core.exceptions import ConfidenceThresholdError

    exc = ConfidenceThresholdError("PERSON", 0.3, 0.8)
    assert exc.confidence == 0.3
    assert exc.threshold == 0.8
    assert "0.30" in str(exc)
    assert "0.80" in str(exc)
    assert isinstance(exc, SafetyCheckError)


def test_label_transition_error():
    from app.core.exceptions import LabelTransitionError

    exc = LabelTransitionError("PERSON", "PUBLIC", "CONFIDENTIAL")
    assert exc.from_label == "PUBLIC"
    assert exc.to_label == "CONFIDENTIAL"
    assert "PUBLIC" in str(exc)
    assert "CONFIDENTIAL" in str(exc)
    assert isinstance(exc, SafetyCheckError)


# ─── Pipeline exceptions ──────────────────────────────────────────────────────


def test_pipeline_error_attributes():
    exc = PipelineError("batch-123", "scan", "timeout")
    assert exc.batch_id == "batch-123"
    assert exc.stage == "scan"
    assert "timeout" in str(exc)
    assert isinstance(exc, CriticalError)


def test_scan_pipeline_error():
    exc = ScanPipelineError("batch-abc", "NER model crash")
    assert exc.batch_id == "batch-abc"
    assert "NER model crash" in str(exc)
    assert isinstance(exc, PipelineError)


def test_apply_pipeline_error():
    exc = ApplyPipelineError("batch-xyz", "mapping not found")
    assert exc.batch_id == "batch-xyz"
    assert "mapping not found" in str(exc)
    assert isinstance(exc, PipelineError)


def test_batch_state_error():
    exc = BatchStateError("batch-001", "pending", "apply")
    assert exc.batch_id == "batch-001"
    assert exc.current_state == "pending"
    assert "apply" in str(exc)
    assert isinstance(exc, CriticalError)


# ─── Crypto exceptions ────────────────────────────────────────────────────────


def test_crypto_error_attributes():
    exc = CryptoError("encryption", "key too short")
    assert exc.operation == "encryption"
    assert "key too short" in str(exc)
    assert isinstance(exc, CriticalError)


def test_encryption_error():
    exc = EncryptionError("AES-GCM failed")
    assert exc.operation == "encryption"
    assert "AES-GCM failed" in str(exc)
    assert isinstance(exc, CryptoError)


def test_decryption_error():
    exc = DecryptionError("invalid tag")
    assert exc.operation == "decryption"
    assert "invalid tag" in str(exc)
    assert isinstance(exc, CryptoError)


def test_invalid_passphrase_error():
    exc = InvalidPassphraseError("passphrase too short")
    assert exc.operation == "passphrase_validation"
    assert "passphrase too short" in str(exc)
    assert isinstance(exc, CryptoError)


def test_mapping_file_error():
    exc = MappingFileError("file corrupted")
    assert exc.operation == "mapping_file_access"
    assert "file corrupted" in str(exc)
    assert isinstance(exc, CryptoError)


# ─── Batch management exceptions ─────────────────────────────────────────────


def test_batch_error_attributes():
    exc = BatchError("batch-999", "disk full")
    assert exc.batch_id == "batch-999"
    assert "disk full" in str(exc)
    assert isinstance(exc, CriticalError)


def test_batch_not_found_error():
    exc = BatchNotFoundError("batch-404")
    assert exc.batch_id == "batch-404"
    assert "not found" in str(exc).lower()
    assert isinstance(exc, BatchError)


def test_batch_already_exists_error():
    exc = BatchAlreadyExistsError("batch-dup")
    assert exc.batch_id == "batch-dup"
    assert "already exists" in str(exc).lower()
    assert isinstance(exc, BatchError)


def test_batch_storage_error():
    exc = BatchStorageError("batch-fs", "permission denied")
    assert exc.batch_id == "batch-fs"
    assert "permission denied" in str(exc)
    assert isinstance(exc, BatchError)


def test_batch_cleanup_error():
    exc = BatchCleanupError("batch-clean", "rmtree failed")
    assert exc.batch_id == "batch-clean"
    assert "rmtree failed" in str(exc)
    assert isinstance(exc, BatchError)


# ─── Config exceptions ────────────────────────────────────────────────────────


def test_config_error_attributes():
    exc = ConfigError("database", "connection refused")
    assert exc.component == "database"
    assert "connection refused" in str(exc)
    assert isinstance(exc, CriticalError)


def test_dictionary_load_error():
    exc = DictionaryLoadError("names.txt", "file not found")
    assert exc.component == "dictionaries"
    assert "names.txt" in str(exc)
    assert "file not found" in str(exc)
    assert isinstance(exc, ConfigError)


def test_policy_load_error():
    exc = PolicyLoadError("invalid YAML syntax")
    assert exc.component == "policies"
    assert "invalid YAML syntax" in str(exc)
    assert isinstance(exc, ConfigError)


# ─── Helper functions ─────────────────────────────────────────────────────────


def test_exception_to_http_status_parsing_error_returns_400():
    exc = ParsingError("f.txt", "text", "bad")
    assert exception_to_http_status(exc) == 400


def test_exception_to_http_status_detection_error_returns_400():
    exc = DetectionError("NER", "fail")
    assert exception_to_http_status(exc) == 400


def test_exception_to_http_status_transform_error_returns_400():
    exc = TransformError("f.txt", "op", "fail")
    assert exception_to_http_status(exc) == 400


def test_exception_to_http_status_policy_error_returns_400():
    exc = PolicyError("GDPR", "fail")
    assert exception_to_http_status(exc) == 400


def test_exception_to_http_status_safety_check_error_returns_400():
    exc = SafetyCheckError("f.txt", "fail")
    assert exception_to_http_status(exc) == 400


def test_exception_to_http_status_batch_not_found_returns_404():
    # ParsingError matches first (400), but BatchNotFoundError matches second (404)
    # The function checks ParsingError first, then BatchNotFoundError
    # BatchNotFoundError is NOT a ParsingError, so it falls through to 404
    exc = BatchNotFoundError("batch-404")
    assert exception_to_http_status(exc) == 404


def test_exception_to_http_status_batch_already_exists_returns_409():
    exc = BatchAlreadyExistsError("batch-dup")
    assert exception_to_http_status(exc) == 409


def test_exception_to_http_status_pipeline_error_returns_500():
    exc = PipelineError("b", "scan", "fail")
    assert exception_to_http_status(exc) == 500


def test_exception_to_http_status_batch_state_error_returns_500():
    exc = BatchStateError("b", "pending", "apply")
    assert exception_to_http_status(exc) == 500


def test_exception_to_http_status_crypto_error_returns_500():
    exc = CryptoError("enc", "fail")
    assert exception_to_http_status(exc) == 500


def test_exception_to_http_status_batch_error_returns_500():
    exc = BatchError("b", "fail")
    assert exception_to_http_status(exc) == 500


def test_exception_to_http_status_config_error_returns_500():
    exc = ConfigError("db", "fail")
    assert exception_to_http_status(exc) == 500


def test_exception_to_http_status_unknown_exception_returns_500():
    exc = ValueError("unexpected")
    assert exception_to_http_status(exc) == 500


def test_exception_to_detail_recoverable():
    exc = ParsingError("f.txt", "text", "bad")
    detail = exception_to_detail(exc)
    assert detail["error_type"] == "ParsingError"
    assert "f.txt" in detail["message"]
    assert detail["detail"]["is_recoverable"] is True
    assert detail["detail"]["is_critical"] is False


def test_exception_to_detail_critical():
    exc = BatchNotFoundError("batch-x")
    detail = exception_to_detail(exc)
    assert detail["error_type"] == "BatchNotFoundError"
    assert detail["detail"]["is_recoverable"] is False
    assert detail["detail"]["is_critical"] is True


def test_exception_to_detail_plain_exception():
    exc = ValueError("plain error")
    detail = exception_to_detail(exc)
    assert detail["error_type"] == "ValueError"
    assert detail["message"] == "plain error"
    assert detail["detail"]["is_recoverable"] is False
    assert detail["detail"]["is_critical"] is False
