"""
Modelli Pydantic per il Local Pseudonymization Tool.
Definisce le strutture dati usate nell'API e nella pipeline.
"""
from __future__ import annotations
from typing import Optional, Dict, List, Any
from enum import Enum
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone


# ─── Enumerazioni ────────────────────────────────────────────────────────────

class BatchMode(str, Enum):
    LIGHT = "light"
    STRICT = "strict"


class BatchStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    REVIEW = "review"
    APPLYING = "applying"
    DONE = "done"
    ERROR = "error"


class FileStatus(str, Enum):
    QUEUED = "queued"
    PARSED = "parsed"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"

    @classmethod
    def _missing_(cls, value):
        """Accetta sia minuscolo che maiuscolo (es. 'ACCEPT' -> ReviewAction.ACCEPT)."""
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member
        return None


class EntityType(str, Enum):
    # Entità di rete
    EMAIL = "EMAIL"
    IPV4 = "IPV4"
    IPV6 = "IPV6"
    URL = "URL"
    HOSTNAME = "HOSTNAME"
    # Identità
    PERSON = "PERSON"
    LDAP_PERSON = "LDAP_PERSON"      # Fullname da LDAP (nome+cognome come entità unica)
    ACCOUNT = "ACCOUNT"              # cn/account da LDAP
    USERNAME = "USERNAME"
    UPN = "UPN"                      # User Principal Name (user@domain.tld)
    # Identificativi IT italiani
    CODICE_FISCALE = "CODICE_FISCALE"
    PARTITA_IVA = "PARTITA_IVA"
    PHONE = "PHONE"
    # Entità Windows/AD
    LDAP_DN = "LDAP_DN"              # Distinguished Name LDAP
    WINDOWS_SID = "WINDOWS_SID"     # Security Identifier Windows
    UNC_PATH = "UNC_PATH"            # Universal Naming Convention path
    WINDOWS_PATH = "WINDOWS_PATH"   # Percorso Windows (C:\...)
    LINUX_PATH = "LINUX_PATH"        # Percorso Linux (/home/...)
    # Email headers
    MAIL_HEADER = "MAIL_HEADER"      # From:/To:/Reply-To:/Message-ID: ecc.
    # Frammenti di dominio identificanti
    DOMAIN_FRAGMENT = "DOMAIN_FRAGMENT"
    # Custom da dizionario
    CUSTOM = "CUSTOM"


class SafetyLabel(str, Enum):
    """Etichetta di sicurezza per batch e card. Solo informativa, non blocca export."""
    SAFE_TO_UPLOAD = "SAFE_TO_UPLOAD"
    SAFE_WITH_WARNINGS = "SAFE_WITH_WARNINGS"
    NOT_SAFE = "NOT_SAFE"


class PresetName(str, Enum):
    SOC_LOGS = "SOC Logs"
    POLICY_DOCS = "Policy Docs"
    EMAIL_HEADERS = "Email Headers"


# ─── Modelli Dati ─────────────────────────────────────────────────────────────

class BatchConfig(BaseModel):
    mode: BatchMode = BatchMode.LIGHT
    is_dry_run: bool = False
    preset: PresetName = PresetName.SOC_LOGS
    # La passphrase NON viene mai salvata in chiaro; viene usata solo in memoria
    # per cifrare il mapping al momento del download.


class FindingLocation(BaseModel):
    """Posizione del finding nel file sorgente."""
    line: Optional[int] = None
    column_start: Optional[int] = None
    column_end: Optional[int] = None
    sheet_name: Optional[str] = None  # Per XLSX
    cell_ref: Optional[str] = None    # Per XLSX (es. "A1")
    bbox: Optional[List[float]] = None  # Per immagini: [x, y, w, h]
    context_snippet: Optional[str] = None  # Breve frammento di testo circostante


class Finding(BaseModel):
    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_id: str
    entity_type: EntityType
    original_value: str
    canonical_value: str = ""        # Forma normalizzata per il mapping (v2)
    proposed_pseudonym: str
    location: FindingLocation = Field(default_factory=FindingLocation)
    confidence_score: float = Field(ge=0.0, le=1.0)
    detector_name: str
    review_action: ReviewAction = ReviewAction.ACCEPT
    modified_pseudonym: Optional[str] = None
    is_text_input: bool = False      # True se il finding viene da testo incollato

    def model_post_init(self, __context: Any) -> None:
        # Se canonical_value non è impostato, usa original_value
        if not self.canonical_value:
            self.canonical_value = self.original_value

    @property
    def final_pseudonym(self) -> str:
        """Restituisce lo pseudonimo finale in base alla decisione di review."""
        if self.review_action == ReviewAction.REJECT:
            return self.original_value  # Non sostituire
        if self.review_action == ReviewAction.MODIFY and self.modified_pseudonym:
            return self.modified_pseudonym
        return self.proposed_pseudonym


class FileRecord(BaseModel):
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_name: str
    stored_path: str  # Percorso temporaneo sul disco locale
    status: FileStatus = FileStatus.QUEUED
    error_message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    findings_count: int = 0
    is_text_input: bool = False      # True se è testo incollato (non file fisico)
    safety_label: SafetyLabel = SafetyLabel.SAFE_TO_UPLOAD


class Batch(BaseModel):
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    config: BatchConfig = Field(default_factory=BatchConfig)
    status: BatchStatus = BatchStatus.PENDING
    files: List[FileRecord] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)
    error_message: Optional[str] = None
    safety_label: SafetyLabel = SafetyLabel.SAFE_TO_UPLOAD
    residual_warnings: List[str] = Field(default_factory=list)
    policy_hash: Optional[str] = None  # SHA256 della policy usata


# ─── Modelli API Request/Response ─────────────────────────────────────────────

class CreateBatchRequest(BaseModel):
    mode: BatchMode = BatchMode.LIGHT
    is_dry_run: bool = False
    preset: PresetName = PresetName.SOC_LOGS


class ReviewDecisionItem(BaseModel):
    finding_id: str
    action: ReviewAction
    modified_pseudonym: Optional[str] = None


class SubmitReviewRequest(BaseModel):
    decisions: List[ReviewDecisionItem]


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: BatchStatus
    files: List[FileRecord]
    findings_count: int
    error_message: Optional[str] = None
    safety_label: SafetyLabel = SafetyLabel.SAFE_TO_UPLOAD


class FindingsResponse(BaseModel):
    batch_id: str
    findings: List[Finding]
    total: int


class ReportSummary(BaseModel):
    batch_id: str
    started_at: str
    completed_at: str
    mode: str
    preset: str
    is_dry_run: bool
    total_files: int
    files_processed: int
    files_failed: int
    files_with_warnings: int
    total_findings: int
    findings_by_type: Dict[str, int]
    files_detail: List[Dict[str, Any]]
    global_warnings: List[str]
    safety_label: str
    residual_warnings: List[str]
    policy_hash: Optional[str] = None
    app_version: str = "2.0.0-vNext"


# ─── Modelli Console API (testo inline) ──────────────────────────────────────

class CreateConsoleBatchResponse(BaseModel):
    batch_id: str
    passphrase: str          # Passphrase generata dall'app (mostrata UNA SOLA VOLTA)
    created_at: str


class TextScanRequest(BaseModel):
    text: str
    label: str = "testo_incollato"  # Nome descrittivo per la card


class TextScanResponse(BaseModel):
    batch_id: str
    file_id: str
    findings: List[Finding]
    findings_count: int
    safety_label: SafetyLabel


class TextApplyResponse(BaseModel):
    batch_id: str
    file_id: str
    pseudonymized_text: str
    safety_label: SafetyLabel
    residual_warnings: List[str]
    applied_count: int


# ─── Modelli LDAP ─────────────────────────────────────────────────────────────

class LdapConfig(BaseModel):
    enabled: bool = False
    host: str = "localhost"
    port: int = 389
    use_tls: bool = False
    starttls: bool = False
    bind_dn: str = ""
    bind_password: str = ""          # Gestita in memoria, non salvata in chiaro
    base_dn: str = "ou=utenti,o=camera"
    filter: str = "(objectClass=inetOrgPerson)"
    attributes: List[str] = Field(default_factory=lambda: ["givenName", "sn", "cn"])
    refresh_interval_minutes: int = 60
    cache_max_entries: int = 10000
    cache_ttl_minutes: int = 120
    match_surname_only: bool = False  # Se True, matcha anche solo cognome (low confidence)


class LdapTestResult(BaseModel):
    success: bool
    message: str
    entries_count: Optional[int] = None
