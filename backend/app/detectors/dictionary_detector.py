"""
Detector basato su dizionari custom configurabili.
Carica termini da file di testo nella directory config/dictionaries/.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

from app.core.config import DICTIONARIES_DIR
from app.detectors.base import BaseDetector, RawFinding
from app.models.schemas import EntityType
from app.parsers.base import TextChunk

logger = logging.getLogger(__name__)

# Mappa nome file dizionario -> EntityType
DICTIONARY_ENTITY_MAP: Dict[str, EntityType] = {
    "person_names.txt": EntityType.PERSON,
    "hostnames.txt": EntityType.HOSTNAME,
    "domains.txt": EntityType.HOSTNAME,
    "usernames.txt": EntityType.USERNAME,
    "custom_patterns.txt": EntityType.CUSTOM,
    "project_codes.txt": EntityType.CUSTOM,
    "office_names.txt": EntityType.CUSTOM,
    "internal_codes.txt": EntityType.CUSTOM,
}


class DictionaryDetector(BaseDetector):
    """
    Detector che cerca corrispondenze esatte (case-insensitive) da dizionari configurabili.
    I dizionari sono file .txt con un termine per riga nella directory config/dictionaries/.
    """

    def __init__(self, dictionaries_dir: Path = DICTIONARIES_DIR):
        self._dictionaries_dir = dictionaries_dir
        # Lista di (termine, entity_type, nome_dizionario)
        self._terms: List[Tuple[str, EntityType, str]] = []
        self._load_dictionaries()

    def _load_dictionaries(self) -> None:
        """Carica tutti i dizionari dalla directory di configurazione."""
        if not self._dictionaries_dir.exists():
            logger.warning("Directory dizionari non trovata: %s", self._dictionaries_dir)
            return

        for dict_file in sorted(self._dictionaries_dir.glob("*.txt")):
            entity_type = DICTIONARY_ENTITY_MAP.get(dict_file.name, EntityType.CUSTOM)
            try:
                content = dict_file.read_text(encoding="utf-8")
                terms_loaded = 0
                for line in content.splitlines():
                    term = line.strip()
                    if term and not term.startswith("#"):  # Ignora righe vuote e commenti
                        self._terms.append((term, entity_type, dict_file.stem))
                        terms_loaded += 1
                logger.info(
                    "Dizionario '%s' caricato: %d termini (tipo: %s)", dict_file.name, terms_loaded, entity_type.value
                )
            except Exception as e:
                logger.error("Errore nel caricamento del dizionario '%s': %s", dict_file.name, e)

    def reload(self) -> None:
        """Ricarica tutti i dizionari (utile dopo modifiche ai file di configurazione)."""
        self._terms = []
        self._load_dictionaries()

    @property
    def name(self) -> str:
        return "DictionaryDetector"

    @property
    def loaded_terms_count(self) -> int:
        return len(self._terms)

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        if chunk.is_formula:
            return []
        if not self._terms:
            return []

        findings = []
        text_lower = chunk.text.lower()

        for term, entity_type, dict_name in self._terms:
            term_lower = term.lower()
            # Cerca tutte le occorrenze del termine nel testo (word boundary)
            try:
                # Usa word boundary per evitare match parziali
                escaped = re.escape(term_lower)
                pattern = re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)
                for match in pattern.finditer(chunk.text):
                    findings.append(
                        RawFinding(
                            entity_type=entity_type,
                            original_value=match.group(0),
                            source_chunk=chunk,
                            confidence_score=0.98,
                            detector_name=f"DictionaryDetector[{dict_name}]",
                            start_pos=match.start(),
                            end_pos=match.end(),
                        )
                    )
            except re.error:
                # Se il termine contiene caratteri speciali che causano errori regex
                if term_lower in text_lower:
                    idx = text_lower.find(term_lower)
                    findings.append(
                        RawFinding(
                            entity_type=entity_type,
                            original_value=chunk.text[idx : idx + len(term)],
                            source_chunk=chunk,
                            confidence_score=0.95,
                            detector_name=f"DictionaryDetector[{dict_name}]",
                            start_pos=idx,
                            end_pos=idx + len(term),
                        )
                    )

        return findings


# Istanza singleton del detector
_dictionary_detector_instance = None


def get_dictionary_detector() -> DictionaryDetector:
    """Restituisce l'istanza singleton del DictionaryDetector."""
    global _dictionary_detector_instance
    if _dictionary_detector_instance is None:
        _dictionary_detector_instance = DictionaryDetector()
    return _dictionary_detector_instance
