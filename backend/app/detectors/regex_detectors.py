"""
Detector basati su espressioni regolari per entità con pattern strutturati.
"""

import logging
import re
from typing import List

from app.detectors.base import BaseDetector, RawFinding
from app.models.schemas import EntityType
from app.parsers.base import TextChunk

logger = logging.getLogger(__name__)


class RegexDetector(BaseDetector):
    """Detector generico basato su una singola espressione regolare."""

    def __init__(
        self,
        entity_type: EntityType,
        pattern: str,
        confidence: float,
        detector_name: str,
        flags: int = re.IGNORECASE,
        validator=None,
        normalizer=None,
    ):
        self._entity_type = entity_type
        self._pattern = re.compile(pattern, flags)
        self._confidence = confidence
        self._detector_name = detector_name
        self._validator = validator  # Funzione opzionale per validare il match
        self._normalizer = normalizer  # Funzione opzionale per normalizzare il valore (es. lowercase per email)

    @property
    def name(self) -> str:
        return self._detector_name

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        findings = []
        for match in self._pattern.finditer(chunk.text):
            # Usa il primo gruppo di cattura se presente, altrimenti il match completo
            try:
                value = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                start = match.start(1) if match.lastindex and match.lastindex >= 1 else match.start()
                end = match.end(1) if match.lastindex and match.lastindex >= 1 else match.end()
            except IndexError:
                value = match.group(0)
                start = match.start()
                end = match.end()

            # Applica il validatore se presente
            if self._validator and not self._validator(value):
                continue

            # Applica il normalizer se presente (es. lowercase per email)
            if self._normalizer:
                value = self._normalizer(value)

            findings.append(
                RawFinding(
                    entity_type=self._entity_type,
                    original_value=value,
                    source_chunk=chunk,
                    confidence_score=self._confidence,
                    detector_name=self._detector_name,
                    start_pos=start,
                    end_pos=end,
                )
            )
        return findings


# Reti da escludere dalla pseudonimizzazione (non sensibili)
_IPV4_EXCLUDED = {  # nosec B104 - detector data set, not a bind address usage
    "127.0.0.1",  # Loopback
    "0.0.0.0",  # Null
    "255.255.255.255",  # Broadcast
}


def _validate_ipv4(value: str) -> bool:
    """Valida che ogni ottetto di un IPv4 sia nel range 0-255 ed escludi indirizzi non sensibili."""
    try:
        parts = value.split(".")
        if len(parts) != 4:
            return False
        if not all(0 <= int(p) <= 255 for p in parts):
            return False
        # Escludi indirizzi non sensibili
        if value in _IPV4_EXCLUDED:
            return False
        return True
    except (ValueError, AttributeError):
        return False


# Tabelle per il carattere di controllo del Codice Fiscale (D.M. 23/12/1976)
_CF_ODD = {
    "0": 1,
    "1": 0,
    "2": 5,
    "3": 7,
    "4": 9,
    "5": 13,
    "6": 15,
    "7": 17,
    "8": 19,
    "9": 21,
    "A": 1,
    "B": 0,
    "C": 5,
    "D": 7,
    "E": 9,
    "F": 13,
    "G": 15,
    "H": 17,
    "I": 19,
    "J": 21,
    "K": 2,
    "L": 4,
    "M": 18,
    "N": 20,
    "O": 11,
    "P": 3,
    "Q": 6,
    "R": 8,
    "S": 12,
    "T": 14,
    "U": 16,
    "V": 10,
    "W": 22,
    "X": 25,
    "Y": 24,
    "Z": 23,
}
# Posizioni pari: cifre = valore numerico, lettere = posizione alfabetica (A=0)
_CF_EVEN = {c: (int(c) if c.isdigit() else ord(c) - ord("A")) for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"}


def _validate_codice_fiscale(value: str) -> bool:
    """
    Validazione del Codice Fiscale italiano.
    Verifica struttura e carattere di controllo (checksum ufficiale D.M. 23/12/1976).
    """
    cf = value.upper()
    if len(cf) != 16:
        return False
    pattern = re.compile(r"^[A-Z]{6}[0-9]{2}[A-EHLMPRST][0-9]{2}[A-Z][0-9]{3}[A-Z]$")
    if not pattern.match(cf):
        return False
    total = sum(_CF_ODD[ch] if i % 2 == 0 else _CF_EVEN[ch] for i, ch in enumerate(cf[:15]))
    return cf[15] == chr(ord("A") + total % 26)


def _validate_partita_iva(value: str) -> bool:
    """
    Validazione della Partita IVA italiana con algoritmo di Luhn.
    """
    if not re.match(r"^\d{11}$", value):
        return False
    s = 0
    for i in range(0, 10, 2):
        s += int(value[i])
    for i in range(1, 10, 2):
        d = int(value[i]) * 2
        s += d if d < 10 else d - 9
    check = (10 - (s % 10)) % 10
    return check == int(value[10])


# ─── Istanze dei Detector ─────────────────────────────────────────────────────

EMAIL_DETECTOR = RegexDetector(
    entity_type=EntityType.EMAIL,
    pattern=r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b",
    confidence=0.95,
    detector_name="RegexEmailDetector",
    normalizer=lambda s: s.lower(),  # Normalize email to lowercase for consistent pseudonymization
)

IPV4_DETECTOR = RegexDetector(
    entity_type=EntityType.IPV4,
    pattern=r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
    confidence=1.0,
    detector_name="RegexIPv4Detector",
    flags=0,
    validator=_validate_ipv4,
)

IPV6_DETECTOR = RegexDetector(
    entity_type=EntityType.IPV6,
    # Pattern che copre le forme più comuni di IPv6
    pattern=(
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"  # Full
        r"|\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b"  # Trailing ::
        r"|\b::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b"  # Leading ::
        r"|\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b"  # Mixed
        r"|\b(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}\b"
        r"|\b(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}\b"
        r"|\b(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}\b"
        r"|\b(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}\b"
        r"|\b[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}\b"
        # IPv4-mapped
        r"|\b::(?:[fF]{4}(?::0{1,4})?:)?"
        r"(?:25[0-5]|(?:2[0-4]|1?[0-9])?[0-9])"
        r"(?:\.(?:25[0-5]|(?:2[0-4]|1?[0-9])?[0-9])){3}\b"
    ),
    confidence=0.90,
    detector_name="RegexIPv6Detector",
)

URL_DETECTOR = RegexDetector(
    entity_type=EntityType.URL,
    pattern=r"https?://[^\s\"'<>]+",
    confidence=0.90,
    detector_name="RegexUrlDetector",
    flags=re.IGNORECASE,
)

HOSTNAME_DETECTOR = RegexDetector(
    entity_type=EntityType.HOSTNAME,
    # Hostname/FQDN: almeno due label separate da punto, nessuno spazio
    pattern=r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.){2,}[a-zA-Z]{2,}\b",
    confidence=0.80,
    detector_name="RegexHostnameDetector",
)

CODICE_FISCALE_DETECTOR = RegexDetector(
    entity_type=EntityType.CODICE_FISCALE,
    pattern=r"\b[A-Z]{6}[0-9]{2}[A-EHLMPRST][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
    confidence=1.0,
    detector_name="RegexCodiceFiscaleDetector",
    flags=re.IGNORECASE,
    validator=_validate_codice_fiscale,
)

PARTITA_IVA_DETECTOR = RegexDetector(
    entity_type=EntityType.PARTITA_IVA,
    # Pattern con contesto: P.IVA/PI/Partita IVA seguito da numero a 11 cifre
    pattern=r"(?:P\.?\s*IVA|Partita\s+IVA|PI)[:\s]+(?:IT)?([0-9]{11})\b",
    confidence=0.90,
    detector_name="RegexPartitaIvaDetector",
    flags=re.IGNORECASE,
    validator=None,  # Il pattern con contesto è già sufficientemente specifico
)

PHONE_DETECTOR = RegexDetector(
    entity_type=EntityType.PHONE,
    # Numeri di telefono italiani e internazionali.
    # Richiede:
    #   a) prefisso internazionale esplicito (+39, +1, ecc.) oppure
    #   b) contesto testuale (tel, fax, cell, phone, numero, nr, n.) prima del numero
    # Questo evita falsi positivi su date (2024-03-15), timestamp, codici, ecc.
    pattern=(
        # Forma A: prefisso +39 o 0039 esplicito
        r"(?:\+39|0039)[\s\-\.]?(?:\d[\s\-\.]?){9,10}\b"
        # Forma B: prefisso internazionale generico (+1..+999)
        r"|\+[1-9]\d{0,2}[\s\-\.]?(?:\d[\s\-\.]?){6,13}\b"
        # Forma C: contesto testuale esplicito + numero italiano
        r"|(?:(?:tel(?:efono)?|fax|cell(?:ulare)?|mobile|phone"
        r"|numero|num|nr|n\.)\s*[:\.]?\s*)"
        r"(?:0\d{1,4}[\s\-\.]?\d{4,8}"
        r"|3\d{2}[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4})\b"
    ),
    confidence=0.80,
    detector_name="RegexPhoneDetector",
)

USERNAME_DETECTOR = RegexDetector(
    entity_type=EntityType.USERNAME,
    # Username tipici: prefisso @ o pattern comune
    pattern=r"(?:^|[\s,;:])@([a-zA-Z0-9_]{3,30})(?=[\s,;:\"'<>]|$)",
    confidence=0.70,
    detector_name="RegexUsernameDetector",
)

# Lista ordinata di tutti i detector regex (l'ordine influenza la priorità)
ALL_REGEX_DETECTORS = [
    EMAIL_DETECTOR,  # Alta priorità: pattern specifico
    CODICE_FISCALE_DETECTOR,
    PARTITA_IVA_DETECTOR,
    IPV4_DETECTOR,
    IPV6_DETECTOR,
    URL_DETECTOR,  # Prima di HOSTNAME per catturare URL completi
    HOSTNAME_DETECTOR,
    PHONE_DETECTOR,
    USERNAME_DETECTOR,
]
