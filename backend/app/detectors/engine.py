"""
Motore di detection v2: orchestra tutti i detector e gestisce le sovrapposizioni
con priorità per tipo di entità (SOC-grade).
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from app.core.exceptions import DetectionError, DictionaryDetectionError, LDAPDetectionError
from app.core.metrics import DETECTOR_DURATION
from app.detectors.base import RawFinding
from app.detectors.dictionary_detector import get_dictionary_detector
from app.detectors.regex_detectors import ALL_REGEX_DETECTORS
from app.detectors.soc_detectors import SOC_DETECTORS, DomainFragmentDetector
from app.models.schemas import EntityType
from app.parsers.base import ParseResult, TextChunk

logger = logging.getLogger(__name__)

# Max threads per detect_in_chunk call.
# Python's re module releases the GIL during C-level matching, so
# ThreadPoolExecutor gives real parallelism for regex-heavy detectors.
# Capped to avoid thread overhead when the detector list is small.
_DETECTOR_MAX_WORKERS = 8


# ─── Priorità per tipo di entità (più alto = priorità maggiore in overlap) ────
# Email > URL > IP > FQDN > Domain > UPN/Username/ACCOUNT > PERSON(fullname) > Fragment
_ENTITY_PRIORITY: dict = {
    EntityType.EMAIL: 100,
    EntityType.MAIL_HEADER: 98,
    EntityType.URL: 95,
    EntityType.IPV4: 90,
    EntityType.IPV6: 90,
    EntityType.LDAP_DN: 88,
    EntityType.UNC_PATH: 85,
    EntityType.WINDOWS_PATH: 82,
    EntityType.LINUX_PATH: 80,
    EntityType.WINDOWS_SID: 88,
    EntityType.HOSTNAME: 75,
    EntityType.UPN: 72,
    EntityType.USERNAME: 70,
    EntityType.ACCOUNT: 70,
    EntityType.LDAP_PERSON: 65,
    EntityType.PERSON: 60,
    EntityType.CODICE_FISCALE: 85,
    EntityType.PARTITA_IVA: 83,
    EntityType.PHONE: 78,
    EntityType.DOMAIN_FRAGMENT: 30,
    EntityType.CUSTOM: 50,
}


def _get_priority(finding: RawFinding) -> int:
    return _ENTITY_PRIORITY.get(finding.entity_type, 50)


def _resolve_overlaps(findings: List[RawFinding]) -> List[RawFinding]:
    """
    Risolve le sovrapposizioni tra finding nello stesso chunk di testo.
    Strategia v2:
    1. Priorità per tipo entità (tabella _ENTITY_PRIORITY)
    2. A parità di tipo: match più lungo
    3. A parità di lunghezza: confidenza più alta
    """
    if not findings:
        return []

    # Ordina per posizione di inizio, poi per priorità decrescente,
    # poi per lunghezza decrescente, poi per confidenza decrescente
    sorted_findings = sorted(
        findings, key=lambda f: (f.start_pos, -_get_priority(f), -(f.end_pos - f.start_pos), -f.confidence_score)
    )

    resolved = []
    last_end = -1

    for finding in sorted_findings:
        if finding.start_pos >= last_end:
            resolved.append(finding)
            last_end = finding.end_pos
        else:
            # Sovrapposizione: confronta con l'ultimo finding accettato
            if resolved:
                current_priority = _get_priority(resolved[-1])
                new_priority = _get_priority(finding)
                current_len = resolved[-1].end_pos - resolved[-1].start_pos
                new_len = finding.end_pos - finding.start_pos

                # Sostituisci se il nuovo ha priorità più alta,
                # o stessa priorità ma è più lungo
                if new_priority > current_priority or (new_priority == current_priority and new_len > current_len):
                    resolved[-1] = finding
                    last_end = finding.end_pos

    return resolved


def _run_detector(detector, chunk):
    """
    Execute a single detector on a chunk and return timing information.

    Called inside a ThreadPoolExecutor thread. Never raises — exceptions are
    returned as the third element so the caller can log them on the main thread
    (avoids mixing log output from multiple threads) and still record timing.

    Returns:
        (findings, elapsed_seconds, exception_or_None)
    """
    t0 = time.perf_counter()
    try:
        return detector.detect(chunk), time.perf_counter() - t0, None
    except Exception as exc:
        return [], time.perf_counter() - t0, exc


def detect_in_chunk(
    chunk: TextChunk,
    extra_detectors: Optional[List] = None,
) -> List[RawFinding]:
    """
    Esegue tutti i detector su un singolo TextChunk e restituisce i finding deduplicati.

    Detectors are run in parallel via ThreadPoolExecutor.  Python's `re` module
    releases the GIL during C-level pattern matching, so regex-heavy detectors
    gain real CPU parallelism on multi-core workers.  IO-bound detectors (LDAP)
    benefit even more.  The overlap resolver runs on the main thread after all
    futures complete, preserving deterministic output.

    extra_detectors: detector aggiuntivi (es. LdapPersonDetector per il batch corrente).
    """
    if chunk.is_formula:
        return []

    # Build flat detector list once; pre-fetch dict_detector singleton.
    dict_detector = get_dictionary_detector()
    all_detectors: List = [
        *ALL_REGEX_DETECTORS,
        *SOC_DETECTORS,
        dict_detector,
        *(extra_detectors or []),
    ]

    all_findings: List[RawFinding] = []
    n_workers = min(len(all_detectors), _DETECTOR_MAX_WORKERS)

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_to_detector = {
            executor.submit(_run_detector, det, chunk): det
            for det in all_detectors
        }

        for future in as_completed(future_to_detector):
            detector = future_to_detector[future]
            findings, elapsed, exc = future.result()

            # Record timing regardless of success/failure
            DETECTOR_DURATION.labels(detector_name=detector.name).observe(elapsed)

            if exc is not None:
                # Log with the appropriate severity based on exception type
                if isinstance(exc, LDAPDetectionError):
                    logger.warning("LDAP detection error in '%s': %s", detector.name, exc)
                elif isinstance(exc, DictionaryDetectionError):
                    logger.warning("Dictionary detection error in '%s': %s", detector.name, exc)
                elif isinstance(exc, DetectionError):
                    logger.warning("Detection error in '%s': %s", detector.name, exc)
                else:
                    logger.error("Unexpected error in detector '%s': %s", detector.name, exc)
            else:
                all_findings.extend(findings)

    # Resolve overlaps on the main thread (deterministic, order-independent input)
    return _resolve_overlaps(all_findings)


def detect_in_parse_result(
    parse_result: ParseResult,
    extra_detectors: Optional[List] = None,
) -> List[RawFinding]:
    """
    Esegue la detection su tutti i chunk di un ParseResult.
    """
    all_findings: List[RawFinding] = []

    for chunk in parse_result.chunks:
        chunk_findings = detect_in_chunk(chunk, extra_detectors=extra_detectors)
        all_findings.extend(chunk_findings)

    logger.info(
        "Detection completata per '%s': trovati %d finding in %d chunk.",
        parse_result.file_path.name,
        len(all_findings),
        len(parse_result.chunks),
    )

    return all_findings


def detect_in_text(
    text: str,
    extra_detectors: Optional[List] = None,
) -> List[RawFinding]:
    """
    Esegue la detection su testo puro (per console/clipboard input).
    Crea un TextChunk virtuale.
    """

    from app.parsers.base import TextChunk as TC

    # Crea un ParseResult virtuale con un singolo chunk
    chunk = TC(text=text, line_number=1)
    return detect_in_chunk(chunk, extra_detectors=extra_detectors)


def residual_scan(
    text: str,
    extra_detectors: Optional[List] = None,
    synthetic_whitelist: Optional[set] = None,
) -> List[RawFinding]:
    """
    Riesegue la detection su testo già pseudonimizzato per trovare eventuali leak residui.
    Restituisce i finding rimasti (se presenti = warning).

    synthetic_whitelist: insieme di valori pseudonimizzati (es. 'EMAIL_001@pseudo.local')
    che NON devono essere segnalati come residui — sono stati introdotti dalla
    pseudonimizzazione stessa e non sono dati originali.
    """
    all_findings = detect_in_text(text, extra_detectors=extra_detectors)
    if not synthetic_whitelist:
        return all_findings
    # Filtra i finding il cui valore originale è nella whitelist sintetica
    return [
        f
        for f in all_findings
        if f.original_value not in synthetic_whitelist and f.canonical_value not in synthetic_whitelist
    ]


def build_extra_detectors(ldap_enabled: bool = True) -> List:
    """
    Costruisce la lista di detector extra per un batch:
    - LdapPersonDetector (se LDAP abilitato)
    - DomainFragmentDetector (se frammenti configurati)
    """
    detectors = []

    if ldap_enabled:
        try:
            from app.detectors.ldap_detector import LdapPersonDetector, _ldap_config

            if _ldap_config and _ldap_config.enabled:
                detectors.append(LdapPersonDetector())
        except Exception as e:
            logger.warning("LdapPersonDetector non disponibile: %s", e)

    # Domain fragments
    try:
        from app.core.config import DICTIONARIES_DIR

        frag_file = DICTIONARIES_DIR / "domain_fragments.txt"
        if frag_file.exists():
            fragments = [
                line.strip()
                for line in frag_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
            if fragments:
                detectors.append(DomainFragmentDetector(fragments))
    except Exception as e:
        logger.debug("DomainFragmentDetector non caricato: %s", e)

    return detectors


def get_ml_detector():
    """Compatibility accessor for ML detector integrations/tests."""
    try:
        from app.detectors.ml_detector import MLNERDetector

        return MLNERDetector()
    except Exception as e:
        logger.warning("ML detector non disponibile: %s", e)

        class _NoopDetector:
            enabled = False
            name = "ml_ner"

            def detect(self, chunk):
                return []

        return _NoopDetector()
