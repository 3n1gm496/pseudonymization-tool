"""
Test per il parallel file processing nel batch.
"""
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from app.core.pipeline import _process_single_file, run_scan_pipeline
from app.models.schemas import FileRecord, FileStatus, EntityType, Batch, BatchStatus, BatchConfig, BatchMode
from app.pseudonymizer.engine import PseudonymEngine
from app.parsers.base import ParseResult, TextChunk
from app.detectors.base import RawFinding


def test_process_single_file_success(tmp_path):
    """Test che _process_single_file funzioni correttamente."""
    # Crea un file di test
    test_file = tmp_path / "test.txt"
    test_file.write_text("Test document with data@example.com")
    
    file_rec = FileRecord(
        file_id="file_001",
        original_name="test.txt",
        stored_path=str(test_file),
        status=FileStatus.QUEUED
    )
    
    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    
    # Mock parse_file
    with patch('app.core.pipeline.parse_file') as mock_parse:
        mock_parse.return_value = ParseResult(
            file_path=test_file,
            chunks=[TextChunk(text="Test document with data@example.com", source_ref="test")],
            success=True
        )
        
        # Mock detection
        with patch('app.core.pipeline.detect_in_parse_result') as mock_detect:
            chunk = TextChunk(text="Test document with data@example.com", source_ref="test")
            mock_detect.return_value = [
                RawFinding(
                    entity_type=EntityType.EMAIL,
                    original_value="data@example.com",
                    source_chunk=chunk,
                    confidence_score=0.9,
                    detector_name="email",
                    start_pos=19,
                    end_pos=36
                )
            ]
            
            updated_file_rec, findings, parse_result = _process_single_file(file_rec, engine)
            
            assert updated_file_rec.status == FileStatus.PARSED
            assert updated_file_rec.findings_count == 1
            assert len(findings) == 1
            assert parse_result.success is True


def test_process_single_file_parse_failure(tmp_path):
    """Test che _process_single_file gestisca errori di parsing."""
    test_file = tmp_path / "corrupt.pdf"
    test_file.write_text("corrupt content")
    
    file_rec = FileRecord(
        file_id="file_002",
        original_name="corrupt.pdf",
        stored_path=str(test_file),
        status=FileStatus.QUEUED
    )
    
    engine = PseudonymEngine(mode=BatchMode.LIGHT)
    
    # Mock parse fallimento
    with patch('app.core.pipeline.parse_file') as mock_parse:
        mock_parse.return_value = ParseResult(
            file_path=test_file,
            success=False,
            error_message="Corrupt PDF"
        )
        
        updated_file_rec, findings, parse_result = _process_single_file(file_rec, engine)
        
        assert updated_file_rec.status == FileStatus.FAILED
        assert "Corrupt PDF" in updated_file_rec.error_message
        assert len(findings) == 0
        assert parse_result.success is False


def test_parallel_processing_enabled(tmp_path):
    """Test che run_scan_pipeline usi parallel processing quando abilitato."""
    # Create test files
    file1 = tmp_path / "file1.txt"
    file1.write_text("Test 1")
    file2 = tmp_path / "file2.txt"
    file2.write_text("Test 2")
    
    batch = Batch(
        batch_id="batch_001",
        status=BatchStatus.PENDING,
        config=BatchConfig(mode=BatchMode.LIGHT),
        files=[
            FileRecord(file_id="f1", original_name="file1.txt", stored_path=str(file1), status=FileStatus.QUEUED),
            FileRecord(file_id="f2", original_name="file2.txt", stored_path=str(file2), status=FileStatus.QUEUED),
        ]
    )
    
    with patch('app.core.pipeline.get_batch', return_value=batch):
        with patch('app.core.pipeline.update_batch'):
            with patch('app.core.pipeline.get_batch_dir', return_value=tmp_path):
                with patch('app.core.pipeline.PARALLEL_FILE_PROCESSING', True):
                    with patch('app.core.pipeline._process_single_file') as mock_process:
                        # Mock _process_single_file per ritornare risultati mock
                        def process_mock(file_rec, engine):
                            parse_result = ParseResult(file_path=Path(file_rec.stored_path), success=True)
                            file_rec.status = FileStatus.PARSED
                            file_rec.findings_count = 0
                            return file_rec, [], parse_result
                        
                        mock_process.side_effect = process_mock
                        
                        result = run_scan_pipeline("batch_001")
                        
                        # Verifica che _process_single_file sia stato chiamato per entrambi i file
                        assert mock_process.call_count == 2
                        assert result.status == BatchStatus.REVIEW


def test_sequential_processing_fallback(tmp_path):
    """Test che run_scan_pipeline usi sequential processing quando parallel è disabilitato."""
    file1 = tmp_path / "file1.txt"
    file1.write_text("Test 1")
    
    batch = Batch(
        batch_id="batch_002",
        status=BatchStatus.PENDING,
        config=BatchConfig(mode=BatchMode.LIGHT),
        files=[
            FileRecord(file_id="f1", original_name="file1.txt", stored_path=str(file1), status=FileStatus.QUEUED),
        ]
    )
    
    with patch('app.core.pipeline.get_batch', return_value=batch):
        with patch('app.core.pipeline.update_batch'):
            with patch('app.core.pipeline.get_batch_dir', return_value=tmp_path):
                with patch('app.core.pipeline.PARALLEL_FILE_PROCESSING', False):
                    with patch('app.core.pipeline._process_single_file') as mock_process:
                        def process_mock(file_rec, engine):
                            parse_result = ParseResult(file_path=Path(file_rec.stored_path), success=True)
                            file_rec.status = FileStatus.PARSED
                            file_rec.findings_count = 0
                            return file_rec, [], parse_result
                        
                        mock_process.side_effect = process_mock
                        
                        result = run_scan_pipeline("batch_002")
                        
                        # Verifica sequential processing
                        assert mock_process.call_count == 1
                        assert result.status == BatchStatus.REVIEW


def test_parallel_processing_error_handling(tmp_path):
    """Test che errori durante parallel processing siano gestiti correttamente."""
    file1 = tmp_path / "file1.txt"
    file1.write_text("Test 1")
    file2 = tmp_path / "file2.txt"
    file2.write_text("Test 2")
    
    batch = Batch(
        batch_id="batch_003",
        status=BatchStatus.PENDING,
        config=BatchConfig(mode=BatchMode.LIGHT),
        files=[
            FileRecord(file_id="f1", original_name="file1.txt", stored_path=str(file1), status=FileStatus.QUEUED),
            FileRecord(file_id="f2", original_name="file2.txt", stored_path=str(file2), status=FileStatus.QUEUED),
        ]
    )
    
    with patch('app.core.pipeline.get_batch', return_value=batch):
        with patch('app.core.pipeline.update_batch'):
            with patch('app.core.pipeline.get_batch_dir', return_value=tmp_path):
                with patch('app.core.pipeline.PARALLEL_FILE_PROCESSING', True):
                    with patch('app.core.pipeline._process_single_file') as mock_process:
                        # Primo file ok, secondo con errore
                        def process_mock(file_rec, engine):
                            if file_rec.file_id == "f1":
                                parse_result = ParseResult(file_path=Path(file_rec.stored_path), success=True)
                                file_rec.status = FileStatus.PARSED
                                file_rec.findings_count = 0
                                return file_rec, [], parse_result
                            else:
                                raise Exception("Simulated error")
                        
                        mock_process.side_effect = process_mock
                        
                        result = run_scan_pipeline("batch_003")
                        
                        # Batch dovrebbe completare anche con errori parziali
                        assert result.status == BatchStatus.REVIEW
                        # Uno dei file dovrebbe essere FAILED
                        failed_files = [f for f in result.files if f.status == FileStatus.FAILED]
                        assert len(failed_files) >= 1
