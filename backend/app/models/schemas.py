"""
Modelli Pydantic per il Local Pseudonymization Tool.
Definisce le strutture dati usate nell'API e nella pipeline.
"""
from __future__ import annotations
from typing import Optional, Dict, List, Any
from enum import Enum
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


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


class EntityType(str, Enum):
    EMAIL = "EMAIL"
    IPV4 = "IPV4"
    IPV6 = "IPV6"
    URL = "URL"
    HOSTNAME = "HOSTNAME"
    PERSON = "PERSON"
    CODICE_FISCALE = "CODICE_FISCALE"
    PARTITA_IVA = "PARTITA_IVA"
    PHONE = "PHONE"
    CUSTOM = "CUSTOM"
    USERNAME = "USERNAME"


# ─── Modelli Dati ─────────────────────────────────────────────────────────────

class BatchConfig(BaseModel):
    mode: BatchMode = BatchMode.LIGHT
    is_dry_run: bool = False
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
    proposed_pseudonym: str
    location: FindingLocation = Field(default_factory=FindingLocation)
    confidence_score: float = Field(ge=0.0, le=1.0)
    detector_name: str
    review_action: ReviewAction = ReviewAction.ACCEPT
    modified_pseudonym: Optional[str] = None

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


class Batch(BaseModel):
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    config: BatchConfig = Field(default_factory=BatchConfig)
    status: BatchStatus = BatchStatus.PENDING
    files: List[FileRecord] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)
    error_message: Optional[str] = None


# ─── Modelli API Request/Response ─────────────────────────────────────────────

class CreateBatchRequest(BaseModel):
    mode: BatchMode = BatchMode.LIGHT
    is_dry_run: bool = False


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


class FindingsResponse(BaseModel):
    batch_id: str
    findings: List[Finding]
    total: int


class ReportSummary(BaseModel):
    batch_id: str
    started_at: str
    completed_at: str
    mode: str
    is_dry_run: bool
    total_files: int
    files_processed: int
    files_failed: int
    files_with_warnings: int
    total_findings: int
    findings_by_type: Dict[str, int]
    files_detail: List[Dict[str, Any]]
    global_warnings: List[str]
