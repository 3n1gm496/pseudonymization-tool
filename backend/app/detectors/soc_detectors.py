"""
Detector SOC-grade v2: UPN, LDAP DN, Windows SID, UNC path, Windows/Linux path,
Mail headers, Domain fragments, e detector con preprocessing/deobfuscation.
"""

import logging
import re
from typing import List

from app.detectors.base import BaseDetector, RawFinding
from app.detectors.preprocessor import canonical_email, deobfuscate
from app.models.schemas import EntityType
from app.parsers.base import TextChunk

logger = logging.getLogger(__name__)


# ─── UPN Detector ─────────────────────────────────────────────────────────────


class UPNDetector(BaseDetector):
    """
    Rileva User Principal Name (UPN): user@domain.tld
    Differisce dall'email per il contesto (dominio AD, non SMTP).
    Pattern: word@word.word (senza punti nella parte locale, tipico AD).
    """

    _PATTERN = re.compile(r"\b([a-zA-Z0-9._\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+)\b")

    @property
    def name(self) -> str:
        return "UPNDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for match in self._PATTERN.finditer(chunk.text):
            value = match.group(1)
            # UPN tipicamente non ha punti nella parte locale (distingue da email)
            # ma li accettiamo comunque con confidence leggermente inferiore
            local, domain = value.split("@", 1)
            confidence = 0.85 if "." not in local else 0.75
            findings.append(
                RawFinding(
                    entity_type=EntityType.UPN,
                    original_value=value,
                    canonical_value=canonical_email(value),
                    source_chunk=chunk,
                    confidence_score=confidence,
                    detector_name=self.name,
                    start_pos=match.start(1),
                    end_pos=match.end(1),
                )
            )
        return findings


# ─── LDAP DN Detector ─────────────────────────────────────────────────────────


class LDAPDNDetector(BaseDetector):
    """
    Rileva Distinguished Name LDAP.
    Es: CN=Mario Rossi,OU=utenti,DC=example,DC=com
    """

    _PATTERN = re.compile(
        # Each component value is capped at 256 chars ({0,255} after the mandatory first char)
        # to prevent pathological backtracking on adversarial input.
        r"\b(?:CN|OU|DC|O|L|ST|C|UID)=[^,\s][^,]{0,255}(?:,(?:CN|OU|DC|O|L|ST|C|UID)=[^,\s][^,]{0,255})+",
        re.IGNORECASE,
    )

    @property
    def name(self) -> str:
        return "LDAPDNDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for match in self._PATTERN.finditer(chunk.text):
            value = match.group(0)
            findings.append(
                RawFinding(
                    entity_type=EntityType.LDAP_DN,
                    original_value=value,
                    canonical_value=value.lower(),
                    source_chunk=chunk,
                    confidence_score=0.92,
                    detector_name=self.name,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )
        return findings


# ─── Windows SID Detector ─────────────────────────────────────────────────────


class WindowsSIDDetector(BaseDetector):
    """
    Rileva Windows Security Identifier (SID).
    Es: S-1-5-21-3623811015-3361044348-30300820-1013
    """

    _PATTERN = re.compile(r"\bS-1-[0-9]+-(?:[0-9]+-)*[0-9]+\b")

    @property
    def name(self) -> str:
        return "WindowsSIDDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for match in self._PATTERN.finditer(chunk.text):
            value = match.group(0)
            # Un SID valido ha almeno 3 componenti dopo S-1-
            parts = value.split("-")
            if len(parts) < 4:
                continue
            findings.append(
                RawFinding(
                    entity_type=EntityType.WINDOWS_SID,
                    original_value=value,
                    canonical_value=value,
                    source_chunk=chunk,
                    confidence_score=0.95,
                    detector_name=self.name,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )
        return findings


# ─── UNC Path Detector ────────────────────────────────────────────────────────


class UNCPathDetector(BaseDetector):
    """
    Rileva UNC path (Universal Naming Convention).
    Es: \\\\server\\share\\path  oppure //server/share/path
    """

    _PATTERN = re.compile(r'(?:\\\\|//)[a-zA-Z0-9_\-\.]+(?:[/\\][^\s,;"\'<>|*?]+)*')

    @property
    def name(self) -> str:
        return "UNCPathDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for match in self._PATTERN.finditer(chunk.text):
            value = match.group(0)
            findings.append(
                RawFinding(
                    entity_type=EntityType.UNC_PATH,
                    original_value=value,
                    canonical_value=value.lower().replace("\\", "/"),
                    source_chunk=chunk,
                    confidence_score=0.90,
                    detector_name=self.name,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )
        return findings


# ─── Windows Path Detector ────────────────────────────────────────────────────


class WindowsPathDetector(BaseDetector):
    """
    Rileva percorsi Windows assoluti.
    Es: C:\\Users\\mario.rossi\\Documents\\report.docx
    """

    _PATTERN = re.compile(r'\b[A-Za-z]:\\(?:[^\s<>:"/\\|?*\x00-\x1f]+\\)*[^\s<>:"/\\|?*\x00-\x1f]*')

    @property
    def name(self) -> str:
        return "WindowsPathDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for match in self._PATTERN.finditer(chunk.text):
            value = match.group(0)
            # Deve avere almeno un separatore per essere un path reale
            if "\\" not in value[2:]:
                continue
            findings.append(
                RawFinding(
                    entity_type=EntityType.WINDOWS_PATH,
                    original_value=value,
                    canonical_value=value.lower().replace("\\", "/"),
                    source_chunk=chunk,
                    confidence_score=0.85,
                    detector_name=self.name,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )
        return findings


# ─── Linux Path Detector ──────────────────────────────────────────────────────


class LinuxPathDetector(BaseDetector):
    """
    Rileva percorsi Linux/Unix assoluti con componenti identificanti.
    Es: /home/mario.rossi/.ssh/id_rsa  /etc/passwd  /var/log/auth.log
    """

    # Percorsi che iniziano con /home/, /root/, /etc/, /var/, /tmp/, /opt/, /srv/
    _PATTERN = re.compile(
        r'(?:^|(?<=\s)|(?<=[\'"(,;]))(?:/(?:home|root|etc|var|tmp|opt|srv|usr|proc|sys|dev|mnt|media|run)'
        r'(?:/[^\s<>"\'|,;)]+)+)',
        re.MULTILINE,
    )

    @property
    def name(self) -> str:
        return "LinuxPathDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for match in self._PATTERN.finditer(chunk.text):
            value = match.group(0).strip()
            if len(value) < 5:
                continue
            findings.append(
                RawFinding(
                    entity_type=EntityType.LINUX_PATH,
                    original_value=value,
                    canonical_value=value,
                    source_chunk=chunk,
                    confidence_score=0.80,
                    detector_name=self.name,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )
        return findings


# ─── Mail Headers Detector ────────────────────────────────────────────────────


class MailHeadersDetector(BaseDetector):
    """
    Rileva valori sensibili nei mail headers: From, To, Reply-To, Received, Message-ID.
    Estrae l'indirizzo email o il valore identificante dal header.
    """

    # Matcha righe di header con valori email o identificativi
    _HEADER_PATTERN = re.compile(
        r"^(?:From|To|Cc|Bcc|Reply-To|Sender|Return-Path|Received|Message-ID|X-Originating-IP)" r"\s*:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    # Estrae email dal valore del header
    _EMAIL_IN_HEADER = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

    @property
    def name(self) -> str:
        return "MailHeadersDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for header_match in self._HEADER_PATTERN.finditer(chunk.text):
            header_value = header_match.group(1).strip()
            header_start = header_match.start(1)
            # Estrai email dal valore del header
            for email_match in self._EMAIL_IN_HEADER.finditer(header_value):
                email = email_match.group(0)
                abs_start = header_start + email_match.start()
                abs_end = header_start + email_match.end()
                findings.append(
                    RawFinding(
                        entity_type=EntityType.MAIL_HEADER,
                        original_value=email,
                        canonical_value=canonical_email(email),
                        source_chunk=chunk,
                        confidence_score=0.95,
                        detector_name=self.name,
                        start_pos=abs_start,
                        end_pos=abs_end,
                    )
                )
        return findings


# ─── Deobfuscated Detector Wrapper ────────────────────────────────────────────


class DeobfuscatedDetector(BaseDetector):
    """
    Wrapper che esegue un detector su testo deobfuscato.
    Quando trova un match nel testo deobfuscato, cerca la corrispondente
    posizione nel testo originale (best-effort).
    """

    def __init__(self, inner_detector: BaseDetector):
        self._inner = inner_detector

    @property
    def name(self) -> str:
        return f"Deobf_{self._inner.name}"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []

        deobf_text = deobfuscate(chunk.text)
        if deobf_text == chunk.text:
            return []  # Nessuna deobfuscation necessaria, evita duplicati

        # Crea un chunk virtuale con il testo deobfuscato
        from app.parsers.base import TextChunk as TC

        deobf_chunk = TC(
            text=deobf_text,
            line_number=chunk.line_number,
            sheet_name=chunk.sheet_name,
            cell_ref=chunk.cell_ref,
            bbox=chunk.bbox,
            is_formula=chunk.is_formula,
        )

        raw_findings = self._inner.detect(deobf_chunk)

        # Aggiorna i finding: original_value = testo originale offuscato,
        # canonical_value = valore deobfuscato (per mapping)
        result = []
        for f in raw_findings:
            # Cerca il testo originale offuscato nella posizione corrispondente
            # (best-effort: usa il canonical_value come chiave di mapping)
            result.append(
                RawFinding(
                    entity_type=f.entity_type,
                    original_value=f.original_value,  # Valore deobfuscato (per sostituzione)
                    canonical_value=f.canonical_value,
                    source_chunk=chunk,  # Chunk originale
                    confidence_score=f.confidence_score * 0.95,  # Lieve penalità per deobf
                    detector_name=self.name,
                    start_pos=f.start_pos,
                    end_pos=f.end_pos,
                )
            )
        return result


# ─── Domain Fragment Detector ─────────────────────────────────────────────────


class DomainFragmentDetector(BaseDetector):
    """
    Detector per frammenti di dominio identificanti (configurabile).
    Matcha substring nel testo con confidence medium/low.
    I frammenti sono caricati dal dizionario 'domain_fragments.txt'.
    """

    def __init__(self, fragments: List[str]):
        self._fragments = [f.strip().lower() for f in fragments if f.strip() and not f.startswith("#")]
        # Compila un pattern per ogni frammento (word boundary o substring)
        self._patterns = []
        for frag in self._fragments:
            try:
                # Usa word boundary se il frammento è alfanumerico, altrimenti substring
                if re.match(r"^[a-zA-Z0-9\-]+$", frag):
                    pat = re.compile(r"\b" + re.escape(frag) + r"\b", re.IGNORECASE)
                else:
                    pat = re.compile(re.escape(frag), re.IGNORECASE)
                self._patterns.append((frag, pat))
            except re.error:
                pass

    @property
    def name(self) -> str:
        return "DomainFragmentDetector"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula or not self._patterns:
            return []
        findings = []
        for frag, pattern in self._patterns:
            for match in pattern.finditer(chunk.text):
                value = match.group(0)
                findings.append(
                    RawFinding(
                        entity_type=EntityType.DOMAIN_FRAGMENT,
                        original_value=value,
                        canonical_value=value.lower(),
                        source_chunk=chunk,
                        confidence_score=0.60,  # Medium/low confidence
                        detector_name=self.name,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )
        return findings


# ─── Lista detector SOC ───────────────────────────────────────────────────────

SOC_DETECTORS: List[BaseDetector] = [
    UPNDetector(),
    LDAPDNDetector(),
    WindowsSIDDetector(),
    UNCPathDetector(),
    WindowsPathDetector(),
    LinuxPathDetector(),
    MailHeadersDetector(),
]
