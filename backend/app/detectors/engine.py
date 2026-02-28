"""
Motore di detection: orchestra tutti i detector e gestisce le sovrapposizioni.
"""
import logging
from typing import List, Optional

from app.detectors.base import RawFinding
from app.detectors.regex_detectors import ALL_REGEX_DETECTORS
from app.detectors.dictionary_detector import get_dictionary_detector
from app.detectors.cache import get_detector_cache
from app.parsers.base import ParseResult, TextChunk

logger = logging.getLogger(__name__)

# ML detector singleton
_ml_detector_instance: Optional[object] = None


def get_ml_detector():
    """Get ML NER detector singleton instance."""
    global _ml_detector_instance
    if _ml_detector_instance is None:
        try:
            from app.detectors.ml_detector import MLNERDetector
            _ml_detector_instance = MLNERDetector()
        except Exception as e:
            logger.warning(f"Failed to initialize ML detector: {e}")
            _ml_detector_instance = None
    return _ml_detector_instance


def _resolve_overlaps(findings: List[RawFinding]) -> List[RawFinding]:
    """
    Risolve le sovrapposizioni tra finding nello stesso chunk di testo.
    Strategia: priorità al match più lungo; a parità di lunghezza, priorità alla confidenza più alta.
    Gestisce correttamente tutti i casi di overlapping, inclusi finding con stessa lunghezza.
    """
    if not findings:
        return []

    # Ordina per posizione di inizio, poi per lunghezza decrescente, poi per confidenza decrescente
    sorted_findings = sorted(
        findings,
        key=lambda f: (f.start_pos, -(f.end_pos - f.start_pos), -f.confidence_score)
    )

    resolved = []
    
    for finding in sorted_findings:
        # Verifica se questo finding si sovrappone con qualcuno già selezionato
        overlaps_with_existing = False
        
        for existing in resolved:
            # Check se c'è overlap
            if not (finding.end_pos <= existing.start_pos or finding.start_pos >= existing.end_pos):
                # C'è overlap - confronta lunghezza e confidenza
                finding_len = finding.end_pos - finding.start_pos
                existing_len = existing.end_pos - existing.start_pos
                
                if finding_len > existing_len or (finding_len == existing_len and finding.confidence_score > existing.confidence_score):
                    # Il nuovo finding è migliore, rimuovi quello esistente
                    resolved.remove(existing)
                    resolved.append(finding)
                    overlaps_with_existing = True
                    break
                else:
                    # Quello esistente è migliore o uguale, skip il nuovo
                    overlaps_with_existing = True
                    break
        
        if not overlaps_with_existing:
            resolved.append(finding)
    
    # Riordina per posizione finale
    resolved.sort(key=lambda f: f.start_pos)
    return resolved


def detect_in_chunk(chunk: TextChunk) -> List[RawFinding]:
    """
    Esegue tutti i detector su un singolo TextChunk e restituisce i finding deduplicati.
    Usa il cache per evitare elaborazioni ripetute dello stesso testo.
    """
    if chunk.is_formula:
        return []

    # Cerca nel cache
    cache = get_detector_cache()
    chunk_id = chunk.source_ref or f"chunk_{id(chunk)}"  # Use source_ref as ID
    cached_findings = cache.get(chunk.text, chunk_id)
    if cached_findings is not None:
        return cached_findings

    # Cache miss - esegui la detection
    all_findings: List[RawFinding] = []

    # Esegui i detector regex
    for detector in ALL_REGEX_DETECTORS:
        try:
            chunk_findings = detector.detect(chunk)
            all_findings.extend(chunk_findings)
        except Exception as e:
            logger.error("Errore nel detector '%s': %s", detector.name, e)

    # Esegui il detector dizionario
    try:
        dict_detector = get_dictionary_detector()
        dict_findings = dict_detector.detect(chunk)
        all_findings.extend(dict_findings)
    except Exception as e:
        logger.error("Errore nel DictionaryDetector: %s", e)
    
    # Esegui il ML/NER detector (P2 feature)
    try:
        ml_detector = get_ml_detector()
        if ml_detector and ml_detector.enabled:
            ml_findings = ml_detector.detect(chunk)
            all_findings.extend(ml_findings)
    except Exception as e:
        logger.error("Errore nel MLNERDetector: %s", e)

    # Risolvi le sovrapposizioni
    resolved_findings = _resolve_overlaps(all_findings)

    # Salva nel cache
    cache.put(chunk.text, chunk_id, resolved_findings)

    return resolved_findings


def detect_in_parse_result(parse_result: ParseResult) -> List[RawFinding]:
    """
    Esegue la detection su tutti i chunk di un ParseResult.
    """
    all_findings: List[RawFinding] = []

    for chunk in parse_result.chunks:
        chunk_findings = detect_in_chunk(chunk)
        all_findings.extend(chunk_findings)

    logger.info(
        "Detection completata per '%s': trovati %d finding in %d chunk.",
        parse_result.file_path.name,
        len(all_findings),
        len(parse_result.chunks),
    )

    return all_findings
