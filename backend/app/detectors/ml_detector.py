"""
ML-based Named Entity Recognition detector using spaCy.

Detects entities like:
- PERSON: People names
- ORG: Organizations, companies
- GPE: Geopolitical entities (countries, cities)
- EMAIL: Email addresses (via custom patterns)
- PHONE: Phone numbers (via custom patterns)
"""

import logging
import re
from typing import List, Optional

from app.core import config
from app.core.circuit_breaker import CircuitBreaker
from app.detectors.base import BaseDetector, RawFinding
from app.models.schemas import EntityType
from app.parsers.base import TextChunk

logger = logging.getLogger(__name__)

# Open after 3 consecutive inference failures; half-open after 120 s.
# Prevents the scan pipeline from repeatedly calling a broken spaCy model
# (e.g., memory error, model file corruption) on every chunk.
_ML_CIRCUIT_BREAKER = CircuitBreaker(failure_threshold=3, recovery_timeout=120.0, name="ml_ner")


class MLNERDetector(BaseDetector):
    """
    Machine Learning based NER detector using spaCy.
    """

    def __init__(self):
        """Initialize the ML NER detector."""
        self.enabled = config.ML_NER_ENABLED
        self.model_name = config.ML_NER_MODEL
        self.confidence_threshold = config.ML_NER_CONFIDENCE_THRESHOLD
        self.nlp = None

        if self.enabled:
            try:
                import spacy

                try:
                    self.nlp = spacy.load(self.model_name)
                    logger.info("ML NER detector loaded with model=%s", self.model_name)
                except OSError:
                    logger.warning(
                        "ML NER model '%s' not found. Run: python -m spacy download %s",
                        self.model_name,
                        self.model_name,
                    )
                    self.enabled = False
            except ImportError:
                logger.warning("spaCy not installed. ML NER detector disabled. Run: pip install spacy")
                self.enabled = False

    @property
    def name(self) -> str:
        """Nome identificativo del detector."""
        return "ml_ner"

    def detect(self, chunk: TextChunk) -> List[RawFinding]:
        """
        Detect entities in TextChunk using spaCy NER.

        Args:
            chunk: TextChunk to analyze

        Returns:
            List of RawFinding objects
        """
        if not self.enabled or not self.nlp or chunk.is_formula:
            return []

        # Skip if circuit is open (repeated inference failures); allow trial on HALF-OPEN
        if _ML_CIRCUIT_BREAKER.is_open:
            return []

        findings: List[RawFinding] = []
        text = chunk.text

        try:
            # Process text with spaCy
            doc = self.nlp(text)

            # Extract named entities
            for ent in doc.ents:
                # Map spaCy labels to our EntityType
                entity_type = self._map_entity_label(ent.label_)

                if entity_type and self._should_include_entity(ent):
                    findings.append(
                        RawFinding(
                            entity_type=entity_type,
                            original_value=ent.text,
                            source_chunk=chunk,
                            confidence_score=self._calculate_confidence(ent),
                            detector_name=self.name,
                            start_pos=ent.start_char,
                            end_pos=ent.end_char,
                        )
                    )

            # Add custom pattern-based detection for emails and phones
            findings.extend(self._detect_emails(chunk))
            findings.extend(self._detect_phones(chunk))

            _ML_CIRCUIT_BREAKER.record_success()

        except Exception as e:
            _ML_CIRCUIT_BREAKER.record_failure()
            logger.error("ML NER detection error: %s", e)

        return findings

    def _map_entity_label(self, label: str) -> Optional[EntityType]:
        """
        Map spaCy entity labels to our EntityType.

        Args:
            label: spaCy entity label (PERSON, ORG, GPE, etc.)

        Returns:
            EntityType or None if not mapped
        """
        mapping = {
            "PERSON": EntityType.PERSON,
            # Note: ORG and LOCATION not in EntityType enum yet,
            # would be added in future enhancement
            # "ORG": EntityType.ORGANIZATION,
            # "GPE": EntityType.LOCATION,
            # "LOC": EntityType.LOCATION,
            # "FAC": EntityType.ORGANIZATION,
        }
        return mapping.get(label)

    def _should_include_entity(self, ent) -> bool:
        """
        Determine if entity should be included based on filters.

        Args:
            ent: spaCy entity

        Returns:
            True if entity should be included
        """
        # Filter out very short entities (likely false positives)
        if len(ent.text.strip()) < 2:
            return False

        # Filter out entities that are just numbers
        if ent.text.strip().isdigit():
            return False

        return True

    def _calculate_confidence(self, ent) -> float:
        """
        Calculate confidence score for entity.

        Args:
            ent: spaCy entity

        Returns:
            Confidence score (0.0 to 1.0)
        """
        # spaCy doesn't provide per-entity confidence out of the box
        # We use heuristics to estimate confidence

        base_confidence = 0.8  # Base confidence for spaCy entities

        # Increase confidence for longer entities
        if len(ent.text) > 10:
            base_confidence += 0.1

        # Increase confidence for capitalized entities
        if ent.text[0].isupper():
            base_confidence += 0.05

        return min(base_confidence, 1.0)

    def _detect_emails(self, chunk: TextChunk) -> List[RawFinding]:
        """
        Detect email addresses using regex patterns.

        Args:
            chunk: TextChunk to search

        Returns:
            List of email findings
        """
        findings = []
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

        for match in re.finditer(email_pattern, chunk.text):
            findings.append(
                RawFinding(
                    entity_type=EntityType.EMAIL,
                    original_value=match.group(),
                    source_chunk=chunk,
                    confidence_score=0.95,
                    detector_name=self.name,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

        return findings

    def _detect_phones(self, chunk: TextChunk) -> List[RawFinding]:
        """
        Detect phone numbers using regex patterns.

        Args:
            chunk: TextChunk to search

        Returns:
            List of phone findings
        """
        findings = []

        # Various phone number patterns
        patterns = [
            r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # US format
            r"\b\(\d{3}\)\s?\d{3}[-.\s]?\d{4}\b",  # (xxx) xxx-xxxx
            r"\b\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b",  # International
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, chunk.text):
                findings.append(
                    RawFinding(
                        entity_type=EntityType.PHONE,
                        original_value=match.group(),
                        source_chunk=chunk,
                        confidence_score=0.90,
                        detector_name=self.name,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

        return findings
