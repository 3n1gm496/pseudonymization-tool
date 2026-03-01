from datetime import datetime, timezone
from pathlib import Path

from app.core import pipeline
from app.core.batch_manager import cleanup_batch, create_batch
from app.models.schemas import Batch, BatchConfig, BatchMode, FileRecord, FileStatus, PresetName, SafetyLabel
from app.parsers.base import ParseResult


def _create_batch_with_file(tmp_path: Path):
    source = tmp_path / "input.txt"
    source.write_text("user@example.com", encoding="utf-8")

    batch = Batch(config=BatchConfig(mode=BatchMode.LIGHT, preset=PresetName.SOC_LOGS))
    file_record = FileRecord(
        original_name="input.txt",
        stored_path=str(source),
        status=FileStatus.PARSED,
        is_text_input=False,
    )
    batch.files = [file_record]
    create_batch(batch)
    return batch, file_record


def test_parse_result_cache_is_batch_scoped():
    parse_1 = ParseResult(file_path=Path("/tmp/a.txt"))
    parse_2 = ParseResult(file_path=Path("/tmp/b.txt"))

    pipeline._cache_parse_result("batch-1", "file-1", parse_1)
    pipeline._cache_parse_result("batch-2", "file-1", parse_2)

    assert pipeline._get_parse_result("batch-1", "file-1") is parse_1
    assert pipeline._get_parse_result("batch-2", "file-1") is parse_2

    pipeline._clear_parse_results("batch-1")
    assert pipeline._get_parse_result("batch-1", "file-1") is None
    assert pipeline._get_parse_result("batch-2", "file-1") is parse_2

    pipeline._clear_parse_results("batch-2")


def test_run_apply_pipeline_clears_batch_parse_cache(monkeypatch, tmp_path):
    batch, file_record = _create_batch_with_file(tmp_path)

    cached_parse = ParseResult(file_path=Path(file_record.stored_path))
    pipeline._cache_parse_result(batch.batch_id, file_record.file_id, cached_parse)

    def fake_transform_file(original_path, output_dir, findings, parse_result):
        out = output_dir / "input.txt"
        out.write_text("masked", encoding="utf-8")
        return out, []

    monkeypatch.setattr(pipeline, "transform_file", fake_transform_file)
    monkeypatch.setattr(pipeline, "compute_safety_label", lambda **kwargs: SafetyLabel.SAFE_TO_UPLOAD)

    zip_path = pipeline.run_apply_pipeline(
        batch.batch_id,
        datetime.now(timezone.utc).isoformat(),
    )

    assert zip_path.exists()
    assert pipeline._get_parse_result(batch.batch_id, file_record.file_id) is None

    cleanup_batch(batch.batch_id)


def test_cleanup_batch_clears_parse_cache(tmp_path):
    batch, file_record = _create_batch_with_file(tmp_path)
    pipeline._cache_parse_result(
        batch.batch_id,
        file_record.file_id,
        ParseResult(file_path=Path(file_record.stored_path)),
    )

    cleanup_batch(batch.batch_id)

    assert pipeline._get_parse_result(batch.batch_id, file_record.file_id) is None
