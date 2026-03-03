"""
Test suite per app/core/console_pipeline.py.

Copre run_text_scan e run_text_apply con mock delle dipendenze esterne
(batch_manager, engine, detectors) per isolare la logica del pipeline.
"""

from unittest.mock import MagicMock, patch

import pytest
from app.core.console_pipeline import run_text_apply, run_text_scan
from app.models.schemas import (
    Batch,
    BatchConfig,
    BatchMode,
    BatchStatus,
    EntityType,
    FileRecord,
    FileStatus,
    Finding,
    FindingLocation,
    PresetName,
    ReviewAction,
    SafetyLabel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_finding(
    file_id="file-001",
    entity_type=EntityType.PERSON,
    confidence=0.95,
    review_action=ReviewAction.ACCEPT,
    pseudonym="PERSON_001",
):
    """Crea un Finding valido per i test."""
    return Finding(
        finding_id="f-001",
        file_id=file_id,
        entity_type=entity_type,
        original_text="Mario Rossi",
        original_value="Mario Rossi",
        proposed_pseudonym=pseudonym,
        confidence_score=confidence,
        location=FindingLocation(start=0, end=11, chunk_index=0),
        review_action=review_action,
        detector_name="regex",
        is_text_input=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_batch():
    """Batch minimale in stato PENDING per test di scan."""
    config = BatchConfig(
        mode=BatchMode.LIGHT,
        preset=PresetName.SOC_LOGS,
    )
    return Batch(
        batch_id="test-batch-001",
        config=config,
        status=BatchStatus.PENDING,
    )


@pytest.fixture
def batch_with_finding(minimal_batch):
    """Batch con un finding per test di apply."""
    finding = make_finding()
    minimal_batch.findings.append(finding)
    return minimal_batch, finding


# ---------------------------------------------------------------------------
# run_text_scan — batch non trovato
# ---------------------------------------------------------------------------


class TestRunTextScanBatchNotFound:
    def test_raises_value_error_when_batch_missing(self):
        """run_text_scan deve sollevare ValueError se il batch non esiste."""
        with patch("app.core.console_pipeline.get_batch", return_value=None):
            with pytest.raises(ValueError, match="Batch non trovato"):
                run_text_scan("nonexistent-batch", "testo di test")


# ---------------------------------------------------------------------------
# run_text_scan — happy path
# ---------------------------------------------------------------------------


class TestRunTextScanHappyPath:
    def _mock_finding(self, entity_type_value="PERSON", confidence=0.95):
        """Crea un MagicMock che simula un finding con entity_type e confidence."""
        m = MagicMock()
        m.entity_type = MagicMock(value=entity_type_value)
        m.confidence_score = confidence
        m.is_text_input = False
        return m

    def test_returns_file_id_findings_safety(self, minimal_batch):
        """run_text_scan deve restituire (file_id, findings, safety_label)."""
        mock_engine = MagicMock()
        mock_finding = self._mock_finding()
        mock_engine.process_findings.return_value = [mock_finding]

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.get_or_create_engine", return_value=mock_engine),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.detect_in_text", return_value=[mock_finding]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=["PERSON"]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch") as mock_update,
            patch("app.core.policies.is_ldap_enabled_for_preset", return_value=False),
        ):

            file_id, findings, safety = run_text_scan("test-batch-001", "Mario Rossi lavora qui")

        assert file_id is not None
        assert len(findings) == 1
        assert safety == SafetyLabel.SAFE_TO_UPLOAD
        mock_update.assert_called_once()

    def test_batch_status_set_to_review_when_pending(self, minimal_batch):
        """Il batch in stato PENDING deve passare a REVIEW dopo lo scan."""
        assert minimal_batch.status == BatchStatus.PENDING

        mock_engine = MagicMock()
        mock_engine.process_findings.return_value = []

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.get_or_create_engine", return_value=mock_engine),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.detect_in_text", return_value=[]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=[]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
            patch("app.core.policies.is_ldap_enabled_for_preset", return_value=False),
        ):

            run_text_scan("test-batch-001", "testo vuoto")

        assert minimal_batch.status == BatchStatus.REVIEW

    def test_findings_filtered_by_disabled_entity_type(self, minimal_batch):
        """I finding con entity_type non abilitato dalla policy devono essere esclusi."""
        mock_engine = MagicMock()
        mock_person = self._mock_finding("PERSON", 0.95)
        mock_ip = self._mock_finding("IP_ADDRESS", 0.90)
        mock_engine.process_findings.return_value = [mock_person, mock_ip]

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.get_or_create_engine", return_value=mock_engine),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.detect_in_text", return_value=[mock_person, mock_ip]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=["PERSON"]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
            patch("app.core.policies.is_ldap_enabled_for_preset", return_value=False),
        ):

            _, findings, _ = run_text_scan("test-batch-001", "Mario Rossi 192.168.1.1")

        assert len(findings) == 1
        assert findings[0].entity_type.value == "PERSON"

    def test_findings_filtered_below_confidence_threshold(self, minimal_batch):
        """I finding sotto la soglia di confidenza devono essere esclusi."""
        mock_engine = MagicMock()
        mock_high = self._mock_finding("PERSON", 0.95)
        mock_low = self._mock_finding("PERSON", 0.30)  # sotto soglia 0.5
        mock_engine.process_findings.return_value = [mock_high, mock_low]

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.get_or_create_engine", return_value=mock_engine),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.detect_in_text", return_value=[mock_high, mock_low]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=["PERSON"]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
            patch("app.core.policies.is_ldap_enabled_for_preset", return_value=False),
        ):

            _, findings, _ = run_text_scan("test-batch-001", "testo")

        assert len(findings) == 1
        assert findings[0].confidence_score == 0.95

    def test_findings_marked_as_text_input(self, minimal_batch):
        """Tutti i finding devono avere is_text_input=True dopo lo scan."""
        mock_engine = MagicMock()
        mock_finding = self._mock_finding()
        mock_finding.is_text_input = False  # inizialmente False
        mock_engine.process_findings.return_value = [mock_finding]

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.get_or_create_engine", return_value=mock_engine),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.detect_in_text", return_value=[mock_finding]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=["PERSON"]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
            patch("app.core.policies.is_ldap_enabled_for_preset", return_value=False),
        ):

            _, findings, _ = run_text_scan("test-batch-001", "testo")

        assert findings[0].is_text_input is True

    def test_file_record_added_to_batch(self, minimal_batch):
        """Un FileRecord virtuale deve essere aggiunto al batch dopo lo scan."""
        assert len(minimal_batch.files) == 0

        mock_engine = MagicMock()
        mock_engine.process_findings.return_value = []

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.get_or_create_engine", return_value=mock_engine),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.detect_in_text", return_value=[]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=[]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
            patch("app.core.policies.is_ldap_enabled_for_preset", return_value=False),
        ):

            file_id, _, _ = run_text_scan("test-batch-001", "testo", label="mio_testo")

        assert len(minimal_batch.files) == 1
        assert minimal_batch.files[0].file_id == file_id
        assert minimal_batch.files[0].original_name == "mio_testo"
        assert minimal_batch.files[0].is_text_input is True


# ---------------------------------------------------------------------------
# run_text_apply — batch non trovato
# ---------------------------------------------------------------------------


class TestRunTextApplyBatchNotFound:
    def test_raises_value_error_when_batch_missing(self):
        """run_text_apply deve sollevare ValueError se il batch non esiste."""
        with patch("app.core.console_pipeline.get_batch", return_value=None):
            with pytest.raises(ValueError, match="Batch non trovato"):
                run_text_apply("nonexistent-batch", "file-001", "testo originale")


# ---------------------------------------------------------------------------
# run_text_apply — happy path
# ---------------------------------------------------------------------------


class TestRunTextApplyHappyPath:
    def test_returns_pseudonymized_text_and_metadata(self, minimal_batch):
        """run_text_apply deve restituire (text, safety, residual_warnings, applied_count)."""
        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.apply_pseudonyms_to_text", return_value=("testo anonimizzato", 2)),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.residual_scan", return_value=[]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=["PERSON"]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_residual_warnings", return_value=[]),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
        ):

            text, safety, residual, count = run_text_apply("test-batch-001", "file-001", "testo originale")

        assert text == "testo anonimizzato"
        assert safety == SafetyLabel.SAFE_TO_UPLOAD
        assert residual == []
        assert count == 2

    def test_file_record_status_set_to_processed(self, minimal_batch):
        """Il FileRecord deve passare a PROCESSED dopo l'apply."""
        file_rec = FileRecord(
            file_id="file-002",
            original_name="test.txt",
            stored_path="",
            status=FileStatus.PARSED,
            is_text_input=True,
        )
        minimal_batch.files.append(file_rec)

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.apply_pseudonyms_to_text", return_value=("output", 0)),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.residual_scan", return_value=[]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=[]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_residual_warnings", return_value=[]),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
        ):

            run_text_apply("test-batch-001", "file-002", "testo")

        assert file_rec.status == FileStatus.PROCESSED

    def test_residual_warnings_appended_to_batch(self, minimal_batch):
        """I residual_warnings devono essere aggiunti al batch."""
        assert minimal_batch.residual_warnings == []

        with (
            patch("app.core.console_pipeline.get_batch", return_value=minimal_batch),
            patch("app.core.console_pipeline.apply_pseudonyms_to_text", return_value=("output", 0)),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.residual_scan", return_value=[MagicMock()]),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=["PERSON"]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_residual_warnings", return_value=["warning-1"]),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_WITH_WARNINGS),
            patch("app.core.console_pipeline.update_batch"),
        ):

            _, _, residual, _ = run_text_apply("test-batch-001", "file-001", "testo")

        assert "warning-1" in residual
        assert "warning-1" in minimal_batch.residual_warnings

    def test_synthetic_whitelist_excludes_rejected_pseudonyms(self, batch_with_finding):
        """I pseudonimi dei finding REJECT non devono essere nella whitelist."""
        batch, finding = batch_with_finding
        finding.review_action = ReviewAction.REJECT
        finding.proposed_pseudonym = "PERSON_001"

        captured_whitelist = {}

        def fake_residual_scan(text, extra_detectors, synthetic_whitelist):
            captured_whitelist["value"] = synthetic_whitelist
            return []

        with (
            patch("app.core.console_pipeline.get_batch", return_value=batch),
            patch("app.core.console_pipeline.apply_pseudonyms_to_text", return_value=("output", 1)),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.residual_scan", side_effect=fake_residual_scan),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=[]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_residual_warnings", return_value=[]),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
        ):

            run_text_apply("test-batch-001", "file-001", "Mario Rossi")

        # PERSON_001 non deve essere nella whitelist perché il finding è REJECT
        assert "PERSON_001" not in captured_whitelist.get("value", set())

    def test_synthetic_whitelist_includes_accepted_pseudonyms(self, batch_with_finding):
        """I pseudonimi dei finding ACCEPT devono essere nella whitelist."""
        batch, finding = batch_with_finding
        finding.review_action = ReviewAction.ACCEPT
        finding.proposed_pseudonym = "PERSON_001"

        captured_whitelist = {}

        def fake_residual_scan(text, extra_detectors, synthetic_whitelist):
            captured_whitelist["value"] = synthetic_whitelist
            return []

        with (
            patch("app.core.console_pipeline.get_batch", return_value=batch),
            patch("app.core.console_pipeline.apply_pseudonyms_to_text", return_value=("output", 1)),
            patch("app.core.console_pipeline.build_extra_detectors", return_value=[]),
            patch("app.core.console_pipeline.residual_scan", side_effect=fake_residual_scan),
            patch("app.core.console_pipeline.get_enabled_entity_types", return_value=[]),
            patch("app.core.console_pipeline.get_confidence_threshold", return_value=0.5),
            patch("app.core.console_pipeline.compute_residual_warnings", return_value=[]),
            patch("app.core.console_pipeline.compute_safety_label", return_value=SafetyLabel.SAFE_TO_UPLOAD),
            patch("app.core.console_pipeline.update_batch"),
        ):

            run_text_apply("test-batch-001", "file-001", "Mario Rossi")

        # PERSON_001 deve essere nella whitelist perché il finding è ACCEPT
        assert "PERSON_001" in captured_whitelist.get("value", set())
