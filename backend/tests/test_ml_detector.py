"""
Test per ML/NER detector.
"""

from unittest.mock import Mock, patch

from app.models.schemas import EntityType
from app.parsers.base import TextChunk


def _make_chunk(text: str) -> TextChunk:
    """Helper to create a TextChunk for testing."""
    return TextChunk(text=text, source_ref="test_ref", is_formula=False, bbox=[0, 0, 100, 100])


def test_ml_detector_disabled_when_spacy_not_available():
    """Test che il detector si disabiliti se spaCy non è disponibile."""
    with patch("app.detectors.ml_detector.config.ML_NER_ENABLED", True):
        with patch("app.detectors.ml_detector.logger"):
            # Mock spacy import to fail
            import sys

            old_modules = sys.modules.copy()
            sys.modules["spacy"] = None

            # This should trigger ImportError handling
            from app.detectors.ml_detector import MLNERDetector

            detector = MLNERDetector()

            # Detector dovrebbe essere disabilitato
            chunk = _make_chunk("John Doe works at Acme Corp")
            findings = detector.detect(chunk)
            assert findings == []

            sys.modules.update(old_modules)


def test_ml_detector_detects_emails():
    """Test rilevamento email addresses."""
    with patch("app.detectors.ml_detector.config.ML_NER_ENABLED", False):
        from app.detectors.ml_detector import MLNERDetector

        detector = MLNERDetector()
        chunk = _make_chunk("Contact john.doe@example.com for info")
        findings = detector._detect_emails(chunk)

        assert len(findings) == 1
        assert findings[0].original_value == "john.doe@example.com"
        assert findings[0].entity_type == EntityType.EMAIL
        assert findings[0].confidence_score >= 0.9


def test_ml_detector_detects_phone_numbers():
    """Test rilevamento numeri di telefono."""
    with patch("app.detectors.ml_detector.config.ML_NER_ENABLED", False):
        from app.detectors.ml_detector import MLNERDetector

        detector = MLNERDetector()

        # Test formato US standard (il più semplice)
        chunk = _make_chunk("Call 555-123-4567 for details")
        findings = detector._detect_phones(chunk)
        assert len(findings) >= 1, "Failed to detect phone in: 555-123-4567"
        assert findings[0].entity_type == EntityType.PHONE
        assert "555-123-4567" in findings[0].original_value


def test_ml_detector_skips_formulas():
    """Test che le formule vengano saltate."""
    with patch("app.detectors.ml_detector.config.ML_NER_ENABLED", False):
        from app.detectors.ml_detector import MLNERDetector

        detector = MLNERDetector()
        chunk = TextChunk(text="=SUM(A1:A10)", source_ref="formula", is_formula=True, bbox=[])

        findings = detector.detect(chunk)
        assert findings == []


def test_ml_detector_integration_with_engine():
    """Test integrazione del ML detector con l'engine."""
    from app.detectors.engine import get_ml_detector

    detector = get_ml_detector()

    # Detector dovrebbe essere creato
    assert detector is not None

    # Dovrebbe avere i metodi richiesti
    assert hasattr(detector, "detect")
    assert hasattr(detector, "enabled")
    assert hasattr(detector, "name")


def test_ml_detector_disabled_integration():
    """Test che il detector disabilitato non produca errori."""
    from app.detectors.engine import detect_in_chunk

    chunk = _make_chunk("John Doe works at john@example.com")

    # Dovrebbe funzionare anche se ML detector è disabled
    findings = detect_in_chunk(chunk)

    # Dovremmo comunque avere findings da altri detector (email regex, etc.)
    assert isinstance(findings, list)


def test_ml_detector_entity_mapping():
    """Test mapping delle entity label spaCy."""
    with patch("app.detectors.ml_detector.config.ML_NER_ENABLED", False):
        from app.detectors.ml_detector import MLNERDetector

        detector = MLNERDetector()

        # Test mappings
        assert detector._map_entity_label("PERSON") == EntityType.PERSON
        # Note: ORG and LOCATION not yet in EntityType enum
        assert detector._map_entity_label("ORG") is None
        assert detector._map_entity_label("GPE") is None
        assert detector._map_entity_label("UNKNOWN") is None


def test_ml_detector_confidence_calculation():
    """Test calcolo confidence score."""
    with patch("app.detectors.ml_detector.config.ML_NER_ENABLED", False):
        from app.detectors.ml_detector import MLNERDetector

        detector = MLNERDetector()

        # Mock entity breve
        mock_short = Mock()
        mock_short.text = "John"

        # Mock entity lunga
        mock_long = Mock()
        mock_long.text = "A very long entity name here"

        conf_short = detector._calculate_confidence(mock_short)
        conf_long = detector._calculate_confidence(mock_long)

        # Confidence dovrebbe essere più alta per entità più lunghe
        assert conf_long > conf_short
        assert 0.0 <= conf_short <= 1.0
        assert 0.0 <= conf_long <= 1.0


def test_ml_detector_filters_short_entities():
    """Test che entità molto corte vengano filtrate."""
    with patch("app.detectors.ml_detector.config.ML_NER_ENABLED", False):
        from app.detectors.ml_detector import MLNERDetector

        detector = MLNERDetector()

        # Mock entità
        mock_short = Mock()
        mock_short.text = "X"

        mock_long = Mock()
        mock_long.text = "John Doe"

        assert detector._should_include_entity(mock_short) == False
        assert detector._should_include_entity(mock_long) == True
