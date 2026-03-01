"""
Exception Taxonomy for Local Pseudonymization Tool

Structured exception hierarchy to distinguish recoverable vs critical failures,
enabling better error diagnostics, telemetry, and incident response.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# BASE EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class PseudonymizationError(Exception):
    """Base exception for all pseudonymization tool errors."""
    pass


class RecoverableError(PseudonymizationError):
    """Error that can be recovered from (e.g., file-level failures in batch)."""
    pass


class CriticalError(PseudonymizationError):
    """Error that indicates critical failure requiring immediate attention."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# PARSING EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class ParsingError(RecoverableError):
    """Base exception for file parsing failures."""
    def __init__(self, filename: str, format_type: str, reason: str):
        self.filename = filename
        self.format_type = format_type
        self.reason = reason
        super().__init__(f"Failed to parse {format_type} file '{filename}': {reason}")


class UnsupportedFormatError(ParsingError):
    """File format is not supported."""
    def __init__(self, filename: str, file_ext: str):
        super().__init__(filename, f"unsupported ({file_ext})", f"Format '{file_ext}' is not supported")


class MalformedFileError(ParsingError):
    """File structure is corrupted or malformed."""
    def __init__(self, filename: str, format_type: str, detail: str):
        super().__init__(filename, format_type, f"Malformed structure: {detail}")


class FileEncodingError(ParsingError):
    """File encoding is not recognized or invalid."""
    def __init__(self, filename: str, encoding: str):
        super().__init__(filename, "text", f"Unsupported encoding: {encoding}")


class PDFParsingError(ParsingError):
    """PDF extraction failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "PDF", reason)


class DocxParsingError(ParsingError):
    """DOCX extraction failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "DOCX", reason)


class XlsxParsingError(ParsingError):
    """XLSX extraction failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "XLSX", reason)


class ImageParsingError(ParsingError):
    """Image extraction/OCR failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "image", reason)


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTION EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class DetectionError(RecoverableError):
    """Base exception for detection failures."""
    def __init__(self, detector_type: str, reason: str):
        self.detector_type = detector_type
        self.reason = reason
        super().__init__(f"Detection failed ({detector_type}): {reason}")


class RegexDetectionError(DetectionError):
    """Regex-based detection failed."""
    def __init__(self, pattern_name: str, reason: str):
        super().__init__(f"regex:{pattern_name}", reason)


class DictionaryDetectionError(DetectionError):
    """Dictionary-based detection failed."""
    def __init__(self, reason: str):
        super().__init__("dictionary", reason)


class LDAPDetectionError(DetectionError):
    """LDAP detection failed."""
    def __init__(self, reason: str):
        super().__init__("ldap", reason)


class LDAPConnectionError(LDAPDetectionError):
    """LDAP server connection failed."""
    def __init__(self, host: str, port: int, reason: str):
        self.host = host
        self.port = port
        super().__init__(f"Cannot connect to {host}:{port} - {reason}")


class LDAPAuthError(LDAPDetectionError):
    """LDAP authentication failed."""
    def __init__(self, reason: str):
        super().__init__(f"Authentication failed: {reason}")


class LDAPPagingError(LDAPDetectionError):
    """LDAP result paging failed."""
    def __init__(self, reason: str):
        super().__init__(f"Paging error: {reason}")


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSFORMATION EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TransformError(RecoverableError):
    """Base exception for content transformation failures."""
    def __init__(self, filename: str, format_type: str, reason: str):
        self.filename = filename
        self.format_type = format_type
        self.reason = reason
        super().__init__(f"Failed to transform {format_type} file '{filename}': {reason}")


class PseudonymizationTransformError(TransformError):
    """Pseudonymization replacement failed in document."""
    def __init__(self, filename: str, format_type: str, entity_count: int, detail: str):
        self.entity_count = entity_count
        super().__init__(filename, format_type, f"Failed to apply {entity_count} replacements: {detail}")


class PDFTransformError(TransformError):
    """PDF transformation failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "PDF", reason)


class DocxTransformError(TransformError):
    """DOCX transformation failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "DOCX", reason)


class XlsxTransformError(TransformError):
    """XLSX transformation failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "XLSX", reason)


class ImageTransformError(TransformError):
    """Image transformation (overlay) failed."""
    def __init__(self, filename: str, reason: str):
        super().__init__(filename, "image", reason)


# ═══════════════════════════════════════════════════════════════════════════════
# POLICY & SAFETY EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class PolicyError(RecoverableError):
    """Policy configuration or validation error."""
    def __init__(self, policy_name: str, reason: str):
        self.policy_name = policy_name
        super().__init__(f"Policy error ({policy_name}): {reason}")


class InvalidPolicyError(PolicyError):
    """Policy configuration is invalid."""
    def __init__(self, policy_name: str, field: str, reason: str):
        super().__init__(policy_name, f"Invalid {field}: {reason}")


class SafetyCheckError(RecoverableError):
    """Safety check (confidence, label transition) failed."""
    def __init__(self, entity_type: str, reason: str):
        self.entity_type = entity_type
        super().__init__(f"Safety check failed ({entity_type}): {reason}")


class ConfidenceThresholdError(SafetyCheckError):
    """Entity confidence below threshold."""
    def __init__(self, entity_type: str, confidence: float, threshold: float):
        self.confidence = confidence
        self.threshold = threshold
        super().__init__(entity_type, f"Confidence {confidence:.2f} < threshold {threshold:.2f}")


class LabelTransitionError(SafetyCheckError):
    """Invalid safety label transition."""
    def __init__(self, entity_type: str, from_label: str, to_label: str):
        self.from_label = from_label
        self.to_label = to_label
        super().__init__(entity_type, f"Invalid transition {from_label} → {to_label}")


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class PipelineError(CriticalError):
    """Base exception for pipeline orchestration failures."""
    def __init__(self, batch_id: str, stage: str, reason: str):
        self.batch_id = batch_id
        self.stage = stage
        super().__init__(f"Pipeline error in batch '{batch_id}' at stage '{stage}': {reason}")


class ScanPipelineError(PipelineError):
    """Scan pipeline failed."""
    def __init__(self, batch_id: str, reason: str):
        super().__init__(batch_id, "scan", reason)


class ApplyPipelineError(PipelineError):
    """Apply pipeline failed."""
    def __init__(self, batch_id: str, reason: str):
        super().__init__(batch_id, "apply", reason)


class BatchStateError(CriticalError):
    """Batch state machine violated."""
    def __init__(self, batch_id: str, current_state: str, invalid_action: str):
        self.batch_id = batch_id
        self.current_state = current_state
        super().__init__(
            f"Invalid action '{invalid_action}' on batch '{batch_id}' in state '{current_state}'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CRYPTOGRAPHY EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class CryptoError(CriticalError):
    """Base exception for cryptographic operations."""
    def __init__(self, operation: str, reason: str):
        self.operation = operation
        super().__init__(f"Crypto error ({operation}): {reason}")


class EncryptionError(CryptoError):
    """Encryption operation failed."""
    def __init__(self, reason: str):
        super().__init__("encryption", reason)


class DecryptionError(CryptoError):
    """Decryption operation failed."""
    def __init__(self, reason: str):
        super().__init__("decryption", reason)


class InvalidPassphraseError(CryptoError):
    """Passphrase validation failed (weak, empty, etc)."""
    def __init__(self, reason: str):
        super().__init__("passphrase_validation", reason)


class MappingFileError(CryptoError):
    """Mapping file (encrypted pseudonyms) is corrupted or inaccessible."""
    def __init__(self, reason: str):
        super().__init__("mapping_file_access", reason)


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH MANAGEMENT EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class BatchError(CriticalError):
    """Base exception for batch management."""
    def __init__(self, batch_id: str, reason: str):
        self.batch_id = batch_id
        super().__init__(f"Batch error ('{batch_id}'): {reason}")


class BatchNotFoundError(BatchError):
    """Batch ID does not exist."""
    def __init__(self, batch_id: str):
        super().__init__(batch_id, "Batch not found")


class BatchAlreadyExistsError(BatchError):
    """Batch ID already exists."""
    def __init__(self, batch_id: str):
        super().__init__(batch_id, "Batch already exists")


class BatchStorageError(BatchError):
    """Batch storage (filesystem) error."""
    def __init__(self, batch_id: str, reason: str):
        super().__init__(batch_id, f"Storage error: {reason}")


class BatchCleanupError(BatchError):
    """Batch cleanup operation failed."""
    def __init__(self, batch_id: str, reason: str):
        super().__init__(batch_id, f"Cleanup error: {reason}")


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION & INITIALIZATION EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class ConfigError(CriticalError):
    """Configuration initialization failed."""
    def __init__(self, component: str, reason: str):
        self.component = component
        super().__init__(f"Configuration error ({component}): {reason}")


class DictionaryLoadError(ConfigError):
    """Dictionary loading failed."""
    def __init__(self, dict_file: str, reason: str):
        super().__init__("dictionaries", f"Failed to load '{dict_file}': {reason}")


class PolicyLoadError(ConfigError):
    """Policy loading failed."""
    def __init__(self, reason: str):
        super().__init__("policies", reason)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Exception to HTTP Status Code Mapping
# ═══════════════════════════════════════════════════════════════════════════════

def exception_to_http_status(exc: Exception) -> int:
    """Map exception to appropriate HTTP status code."""
    if isinstance(exc, (ParsingError, DetectionError, TransformError, PolicyError, SafetyCheckError)):
        return 400  # Bad Request (client/data error)
    elif isinstance(exc, (ParsingError, BatchNotFoundError)):
        return 404  # Not Found
    elif isinstance(exc, BatchAlreadyExistsError):
        return 409  # Conflict
    elif isinstance(exc, (PipelineError, BatchStateError, CryptoError, BatchError, ConfigError)):
        return 500  # Internal Server Error
    else:
        return 500  # Default to 500


def exception_to_detail(exc: Exception) -> dict:
    """Convert exception to API response detail dict."""
    return {
        "error_type": exc.__class__.__name__,
        "message": str(exc),
        "detail": {
            "is_recoverable": isinstance(exc, RecoverableError),
            "is_critical": isinstance(exc, CriticalError),
        }
    }
