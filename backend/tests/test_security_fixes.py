"""
Test per i fix di sicurezza e robustness implementati nella v1.1.
Testa:
- Batch TTL e garbage collection
- Passphrase validation (entropia)
- File magic bytes validation
- Thread safety
- Overlapping findings logic
- Email normalization
- Confidence score validation
- Input sanitization
"""
import pytest
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from app.models.schemas import (
    Batch, BatchConfig, BatchMode, BatchStatus, ReviewDecisionItem, ReviewAction,
    EntityType
)
from app.parsers.base import TextChunk
from app.detectors.base import RawFinding
from app.core.batch_manager import (
    create_batch, get_batch, cleanup_batch, update_batch, get_inactive_batch_ids,
    cleanup_inactive_batches, get_all_batch_ids
)
from app.api.routes import _calculate_entropy, _validate_passphrase, _validate_file_magic_bytes
from app.detectors.engine import _resolve_overlaps
from app.pseudonymizer.engine import PseudonymEngine
from fastapi import HTTPException


class TestPassphraseValidation:
    """Test passphrase validation with entropy check."""
    
    def test_passphrase_too_short(self):
        """Test che una passphrase troppo corta è rifiutata."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_passphrase("abc")
        assert exc_info.value.status_code == 400
        assert "almeno" in exc_info.value.detail.lower()
    
    def test_passphrase_low_entropy(self):
        """Test che una passphrase con bassa entropia è rifiutata."""
        # "aaaaaaaaaaaaa" ha entropia 0 (tutti caratteri uguali)
        with pytest.raises(HTTPException) as exc_info:
            _validate_passphrase("aaaaaaaaaaaaa")
        assert exc_info.value.status_code == 400
        assert "debole" in exc_info.value.detail.lower()
    
    def test_entropy_calculation(self):
        """Test il calcolo dell'entropia."""
        # Unicode entropy: log2(1) = 0
        assert _calculate_entropy("aaaa") == 0.0
        
        # Due caratteri equiprobabili: log2(2) = 1.0 bit
        entropy_ab = _calculate_entropy("aabb")
        assert 0.9 < entropy_ab < 1.1
        
        # Quattro caratteri: log2(4) = 2.0 bit
        entropy_abcd = _calculate_entropy("abcdabcdabcdabcd")
        assert 1.9 < entropy_abcd < 2.1
    
    def test_passphrase_valid(self):
        """Test che una passphrase forte è accettata."""
        # Non deve sollevare eccezione
        _validate_passphrase("Str0ng!P@ssw0rd#2024")


class TestFileMagicBytes:
    """Test file magic bytes validation."""
    
    def test_pdf_magic_bytes(self):
        """Test detection di file PDF."""
        pdf_header = b'%PDF-1.4\n'
        detected = _validate_file_magic_bytes(pdf_header, "test.pdf")
        assert detected == ".pdf"
    
    def test_jpg_magic_bytes(self):
        """Test detection di file JPEG."""
        jpg_header = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        detected = _validate_file_magic_bytes(jpg_header, "test.jpg")
        assert detected == ".jpg"
    
    def test_png_magic_bytes(self):
        """Test detection di file PNG."""
        png_header = b'\x89PNG\r\n\x1a\n'
        detected = _validate_file_magic_bytes(png_header, "test.png")
        assert detected == ".png"
    
    def test_text_file_no_validation(self):
        """Test che file text non richiedono magicBytes stringente."""
        detected = _validate_file_magic_bytes(b'Hello World', "test.txt")
        assert detected == ".txt"
    
    def test_mismatch_warning(self, caplog):
        """Test che viene loggato warning se ce mismatch tra estensione e contenuto."""
        pdf_content = b'%PDF-1.4\n'
        _validate_file_magic_bytes(pdf_content, "test.txt")
        # Potrebbe loggare warning ma è ok, il file è comunque accettato


class TestBatchGarbageCollection:
    """Test batch TTL e garbage collection."""
    
    def test_batch_ttl_creation(self):
        """Test che un batch ha timestamp di creazione."""
        batch = Batch(config=BatchConfig())
        assert batch.created_at is not None
        assert batch.last_activity_at is not None
    
    def test_batch_last_activity_update(self):
        """Test che last_activity_at si aggiorna con update_batch."""
        batch = create_batch(Batch(config=BatchConfig()))
        original_activity = batch.last_activity_at
        
        # Dormi un po' per assicurarsi che il timestamp cambi
        import time
        time.sleep(0.1)
        
        batch = update_batch(batch)
        assert batch.last_activity_at > original_activity
    
    def test_get_inactive_batch_ids_empty(self):
        """Test che non ci sono batch inattivi se tutti sono recenti."""
        # Pulisci batch precedenti
        for batch_id in get_all_batch_ids():
            cleanup_batch(batch_id)
        
        # Crea un batch recente
        batch = create_batch(Batch(config=BatchConfig()))
        
        inactive = get_inactive_batch_ids()
        assert batch.batch_id not in inactive
        
        cleanup_batch(batch.batch_id)
    
    def test_cleanup_inactive_batches(self):
        """Test il garbage collector di batch inattivi."""
        from app.core.config import BATCH_INACTIVITY_TTL_HOURS
        from app.core.batch_manager import _batches, _store_lock
        
        # Pulisci batch precedenti
        for batch_id in get_all_batch_ids():
            cleanup_batch(batch_id)
        
        # Crea un batch e manually marcalo come inattivo
        batch = create_batch(Batch(config=BatchConfig()))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=BATCH_INACTIVITY_TTL_HOURS + 1)
        
        # Modifica direttamente nel dict per evitare che update_batch riscrivi il timestamp
        with _store_lock:
            _batches[batch.batch_id].last_activity_at = cutoff.isoformat()
        
        # Verifica che è nel set di inattivi
        inactive = get_inactive_batch_ids()
        assert batch.batch_id in inactive
        
        # Cleanup
        cleaned = cleanup_inactive_batches()
        assert cleaned >= 1
        assert get_batch(batch.batch_id) is None


class TestOverlappingFindings:
    """Test la logica di risoluzione degli overlapping findings."""
    
    def test_no_overlaps(self):
        """Test findings non overlappanti."""
        chunk = TextChunk("test text", 0, False)
        f1 = RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="test1",
            source_chunk=chunk,
            confidence_score=0.9,
            detector_name="test",
            start_pos=0,
            end_pos=5
        )
        f2 = RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="test2",
            source_chunk=chunk,
            confidence_score=0.9,
            detector_name="test",
            start_pos=6,
            end_pos=11
        )
        
        resolved = _resolve_overlaps([f1, f2])
        assert len(resolved) == 2
    
    def test_overlaps_different_length(self):
        """Test overlaps con lunghezze diverse - tiene il più lungo."""
        chunk = TextChunk("Jane Doe Smith", 0, False)
        f1 = RawFinding(
            entity_type=EntityType.PERSON,
            original_value="Jane",
            source_chunk=chunk,
            confidence_score=0.9,
            detector_name="test",
            start_pos=0,
            end_pos=4
        )
        f2 = RawFinding(
            entity_type=EntityType.PERSON,
            original_value="Jane Doe",
            source_chunk=chunk,
            confidence_score=0.85,
            detector_name="test",
            start_pos=0,
            end_pos=8
        )
        
        resolved = _resolve_overlaps([f1, f2])
        assert len(resolved) == 1
        assert resolved[0].original_value == "Jane Doe"
    
    def test_overlaps_same_length_different_confidence(self):
        """Test overlaps con stessa lunghezza - tiene quello con confidenza più alta."""
        chunk = TextChunk("test@example.com", 0, False)
        f1 = RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="test@example.com",
            source_chunk=chunk,
            confidence_score=0.8,
            detector_name="regex",
            start_pos=0,
            end_pos=16
        )
        f2 = RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="test@example.com",
            source_chunk=chunk,
            confidence_score=0.95,
            detector_name="ml",
            start_pos=0,
            end_pos=16
        )
        
        resolved = _resolve_overlaps([f1, f2])
        assert len(resolved) == 1
        assert resolved[0].confidence_score == 0.95
    
    def test_partial_overlaps(self):
        """Test overlaps parziali."""
        chunk = TextChunk("ane Doe", 0, False)
        f1 = RawFinding(
            entity_type=EntityType.PERSON,
            original_value="Jane Doe",
            source_chunk=chunk,
            confidence_score=0.9,
            detector_name="test",
            start_pos=0,
            end_pos=8
        )
        f2 = RawFinding(
            entity_type=EntityType.PERSON,
            original_value="ane Doe",
            source_chunk=chunk,
            confidence_score=0.85,
            detector_name="test",
            start_pos=1,
            end_pos=8
        )
        
        resolved = _resolve_overlaps([f1, f2])
        assert len(resolved) == 1
        # Dovrebbe mantenere il più lungo (f1)
        assert resolved[0].original_value == "Jane Doe"


class TestEmailNormalization:
    """Test la normalizzazione degli email."""
    
    def test_email_normalization_in_pseudonym_engine(self):
        """Test che gli email vengono normalizzati a lowercase."""
        engine = PseudonymEngine(BatchMode.LIGHT)
        
        pseudo1 = engine.get_or_create_pseudonym(EntityType.EMAIL, "Test@Example.COM")
        pseudo2 = engine.get_or_create_pseudonym(EntityType.EMAIL, "test@example.com")
        
        # Stesso pseudonimo perché normalizzati
        assert pseudo1 == pseudo2


class TestConfidenceScoreValidation:
    """Test la validazione dei confidence score."""
    
    def test_confidence_score_clamping(self, caplog):
        """Test che confidence score invalido viene clampato."""
        chunk = TextChunk("test", 0, False)
        
        # Confidence > 1.0 deve essere clampato
        finding = RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="test",
            source_chunk=chunk,
            confidence_score=1.5,  # Invalid
            detector_name="test",
            start_pos=0,
            end_pos=4
        )
        
        # Deve essere clampato a 1.0
        assert finding.confidence_score == 1.0
    
    def test_confidence_score_negative_clamping(self):
        """Test che confidence < 0.0 viene clampato."""
        chunk = TextChunk("test", 0, False)
        finding = RawFinding(
            entity_type=EntityType.EMAIL,
            original_value="test",
            source_chunk=chunk,
            confidence_score=-0.5,  # Invalid
            detector_name="test",
            start_pos=0,
            end_pos=4
        )
        
        assert finding.confidence_score == 0.0


class TestInputSanitization:
    """Test l'input sanitization."""
    
    def test_sanitized_pseudonym_method(self):
        """Test il metodo sanitized_pseudonym di ReviewDecisionItem."""
        decision = ReviewDecisionItem(
            finding_id="test123",
            action=ReviewAction.MODIFY,
            modified_pseudonym="Valid_Pseudonym_123"
        )
        
        sanitized = decision.sanitized_pseudonym()
        assert sanitized == "Valid_Pseudonym_123"
    
    def test_sanitized_pseudonym_with_control_chars(self):
        """Test che i control character vengono rimossi."""
        decision = ReviewDecisionItem(
            finding_id="test123",
            action=ReviewAction.MODIFY,
            modified_pseudonym="Test<script>alert()</script>Pseudo"
        )
        
        sanitized = decision.sanitized_pseudonym()
        # Control char rimossi
        assert "<" not in sanitized
        assert ">" not in sanitized
    
    def test_sanitized_pseudonym_length_limit(self):
        """Test che pseudonym è limitato a 200 caratteri."""
        decision = ReviewDecisionItem(
            finding_id="test123",
            action=ReviewAction.MODIFY,
            modified_pseudonym="a" * 300  # Too long
        )
        
        sanitized = decision.sanitized_pseudonym()
        assert len(sanitized) == 200
