"""
Comprehensive test suite for core/pipeline.py module.
Target coverage: >80% on pipeline processing, batch management, and result handling.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.exceptions import BatchStateError
from app.core.pipeline import (
    _cache_parse_result,
    _clear_parse_results,
    _filter_findings_by_policy,
    _get_parse_result,
    _parse_results,
    apply_review_decisions,
    run_apply_pipeline,
    run_scan_pipeline,
)
from app.models.schemas import (
    EntityType,
    PresetName,
)
from app.parsers.base import ParseResult


@pytest.fixture
def clear_parse_cache():
    """Clear parse result cache before and after each test."""
    _parse_results.clear()
    yield
    _parse_results.clear()


class TestParseResultCache:
    """Test in-memory cache for ParseResult objects."""

    def test_cache_parse_result_stores_result(self, clear_parse_cache):
        """Test that _cache_parse_result stores parse result."""
        batch_id = "test_batch"
        file_id = "file_001"
        parse_result = ParseResult(
            file_path=Path("/tmp/test.txt"),
            chunks=[],
            warnings=[],
            is_image=False,
            image_path=None,
            success=True,
            error_message=None,
        )

        _cache_parse_result(batch_id, file_id, parse_result)

        assert batch_id in _parse_results
        assert file_id in _parse_results[batch_id]
        assert _parse_results[batch_id][file_id] == parse_result

    def test_get_parse_result_retrieves_cached_result(self, clear_parse_cache):
        """Test that _get_parse_result retrieves cached result."""
        batch_id = "test_batch"
        file_id = "file_001"
        parse_result = ParseResult(
            file_path=Path("/tmp/test.txt"),
            chunks=[],
            warnings=[],
            is_image=False,
            image_path=None,
            success=True,
            error_message=None,
        )

        _cache_parse_result(batch_id, file_id, parse_result)
        retrieved = _get_parse_result(batch_id, file_id)

        assert retrieved == parse_result

    def test_get_parse_result_returns_none_for_missing_batch(self, clear_parse_cache):
        """Test that _get_parse_result returns None for missing batch."""
        result = _get_parse_result("nonexistent_batch", "file_001")
        assert result is None

    def test_get_parse_result_returns_none_for_missing_file(self, clear_parse_cache):
        """Test that _get_parse_result returns None for missing file in batch."""
        batch_id = "test_batch"
        _parse_results[batch_id] = {}

        result = _get_parse_result(batch_id, "nonexistent_file")
        assert result is None

    def test_clear_parse_results_removes_batch_cache(self, clear_parse_cache):
        """Test that _clear_parse_results removes batch from cache."""
        batch_id = "test_batch"
        file_id = "file_001"
        parse_result = ParseResult(
            file_path=Path("/tmp/test.txt"),
            chunks=[],
            warnings=[],
            is_image=False,
            image_path=None,
            success=True,
            error_message=None,
        )

        _cache_parse_result(batch_id, file_id, parse_result)
        assert batch_id in _parse_results

        _clear_parse_results(batch_id)
        assert batch_id not in _parse_results

    def test_clear_parse_results_with_nonexistent_batch(self, clear_parse_cache):
        """Test that _clear_parse_results doesn't raise for nonexistent batch."""
        # Should not raise
        _clear_parse_results("nonexistent_batch")

    def test_multiple_batches_in_cache(self, clear_parse_cache):
        """Test caching for multiple batches simultaneously."""
        batch1_id = "batch_1"
        batch2_id = "batch_2"
        file_id = "file_001"

        parse_result1 = ParseResult(
            file_path=Path("/tmp/test1.txt"),
            chunks=[],
            warnings=[],
            is_image=False,
            image_path=None,
            success=True,
            error_message=None,
        )
        parse_result2 = ParseResult(
            file_path=Path("/tmp/test2.txt"),
            chunks=[],
            warnings=["Warning"],
            is_image=False,
            image_path=None,
            success=True,
            error_message=None,
        )

        _cache_parse_result(batch1_id, file_id, parse_result1)
        _cache_parse_result(batch2_id, file_id, parse_result2)

        assert _get_parse_result(batch1_id, file_id) == parse_result1
        assert _get_parse_result(batch2_id, file_id) == parse_result2

        _clear_parse_results(batch1_id)
        assert batch1_id not in _parse_results
        assert batch2_id in _parse_results


class TestFilterFindingsByPolicy:
    """Test filtering findings based on policy configuration."""

    def test_filter_empty_findings_list(self):
        """Test filtering empty findings list."""
        with patch("app.core.pipeline.get_enabled_entity_types", return_value=[EntityType.PERSON.value]):
            with patch("app.core.pipeline.get_confidence_threshold", return_value=0.8):
                filtered = _filter_findings_by_policy([], PresetName.SOC_LOGS)

        assert filtered == []




class TestApplyReviewDecisionsSimple:
    """Test apply_review_decisions basic functionality."""

    def test_apply_decisions_batch_not_found(self):
        """Test apply_review_decisions with nonexistent batch."""
        with patch("app.core.pipeline.get_batch", return_value=None):
            with pytest.raises(ValueError, match="Batch non trovato"):
                apply_review_decisions("nonexistent_batch", [])





class TestRunScanPipelineEdgeCases:
    """Test edge cases in run_scan_pipeline."""

    def test_scan_pipeline_batch_not_found(self):
        """Test run_scan_pipeline with nonexistent batch."""
        with patch("app.core.pipeline.get_batch", return_value=None):
            with pytest.raises(BatchStateError):
                run_scan_pipeline("nonexistent_batch")


class TestRunApplyPipelineEdgeCases:
    """Test edge cases in run_apply_pipeline."""

    def test_apply_pipeline_batch_not_found(self):
        """Test run_apply_pipeline with nonexistent batch."""
        with patch("app.core.pipeline.get_batch", return_value=None):
            with pytest.raises(BatchStateError):
                run_apply_pipeline("nonexistent_batch", "2026-03-02T10:00:00Z")

