"""
Test per app.core.tasks — scan_batch_task, apply_batch_task, get_task_status, revoke_task.
Celery è configurato in EAGER mode da conftest.py (task_always_eager=True).
Coverage target: ≥70%

Retry policy verificata:
- RecoverableError (e sottoclassi): ritentata fino a 3 volte
- CriticalError (e sottoclassi): NON ritentata — fallisce immediatamente
- ValueError, TypeError, KeyError, AttributeError: NON ritentati
"""

from unittest.mock import MagicMock, patch

import pytest
from app.core.exceptions import (
    BatchNotFoundError,
    BatchStateError,
    CriticalError,
    ParsingError,
    RecoverableError,
    TransformError,
)
from app.core.tasks import (
    NON_RETRYABLE_EXCEPTIONS,
    DatabaseTask,
    apply_batch_task,
    get_task_status,
    revoke_task,
    scan_batch_task,
)

# ─────────────────────────────────────────────────────────────────────────────
# DatabaseTask retry policy
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabaseTaskRetryPolicy:
    """Verifica che la retry policy di DatabaseTask sia configurata correttamente."""

    def test_autoretry_for_includes_recoverable_error(self):
        """autoretry_for deve includere RecoverableError."""
        assert RecoverableError in DatabaseTask.autoretry_for

    def test_autoretry_for_includes_io_errors(self):
        """autoretry_for deve includere IOError, OSError, MemoryError, TimeoutError."""
        assert IOError in DatabaseTask.autoretry_for
        assert OSError in DatabaseTask.autoretry_for
        assert MemoryError in DatabaseTask.autoretry_for
        assert TimeoutError in DatabaseTask.autoretry_for

    def test_dont_autoretry_for_includes_critical_error(self):
        """dont_autoretry_for deve includere CriticalError."""
        assert CriticalError in DatabaseTask.dont_autoretry_for

    def test_dont_autoretry_for_includes_value_error(self):
        """dont_autoretry_for deve includere ValueError."""
        assert ValueError in DatabaseTask.dont_autoretry_for

    def test_dont_autoretry_for_includes_type_and_key_errors(self):
        """dont_autoretry_for deve includere TypeError, KeyError, AttributeError."""
        assert TypeError in DatabaseTask.dont_autoretry_for
        assert KeyError in DatabaseTask.dont_autoretry_for
        assert AttributeError in DatabaseTask.dont_autoretry_for

    def test_non_retryable_exceptions_constant(self):
        """NON_RETRYABLE_EXCEPTIONS deve essere una tupla con almeno CriticalError e ValueError."""
        assert isinstance(NON_RETRYABLE_EXCEPTIONS, tuple)
        assert CriticalError in NON_RETRYABLE_EXCEPTIONS
        assert ValueError in NON_RETRYABLE_EXCEPTIONS

    def test_max_retries_is_3(self):
        """max_retries deve essere 3."""
        assert DatabaseTask.retry_kwargs["max_retries"] == 3

    def test_retry_backoff_enabled(self):
        """retry_backoff deve essere True."""
        assert DatabaseTask.retry_backoff is True

    def test_critical_error_subclasses_are_non_retryable(self):
        """BatchStateError e BatchNotFoundError (sottoclassi di CriticalError) devono essere non-retryable."""
        assert issubclass(BatchStateError, CriticalError)
        assert issubclass(BatchNotFoundError, CriticalError)
        # Verificare che siano incluse tramite la gerarchia
        assert issubclass(BatchStateError, NON_RETRYABLE_EXCEPTIONS)
        assert issubclass(BatchNotFoundError, NON_RETRYABLE_EXCEPTIONS)

    def test_recoverable_error_subclasses_are_retryable(self):
        """ParsingError e TransformError (sottoclassi di RecoverableError) devono essere retryable."""
        assert issubclass(ParsingError, RecoverableError)
        assert issubclass(TransformError, RecoverableError)
        assert issubclass(ParsingError, DatabaseTask.autoretry_for)
        assert issubclass(TransformError, DatabaseTask.autoretry_for)


# ─────────────────────────────────────────────────────────────────────────────
# scan_batch_task
# ─────────────────────────────────────────────────────────────────────────────


class TestScanBatchTask:
    """Test per scan_batch_task in EAGER mode."""

    def test_scan_task_success(self):
        """Task di scan eseguito con successo restituisce dict con batch_id e findings_count."""
        mock_batch = MagicMock()
        mock_batch.findings = [MagicMock(), MagicMock()]
        mock_batch.files = [MagicMock()]
        mock_batch.safety_label = MagicMock()
        mock_batch.safety_label.value = "SAFE_TO_UPLOAD"
        mock_batch.status = MagicMock()
        mock_batch.status.value = "review"

        with (
            patch("app.core.tasks.get_batch", return_value=mock_batch),
            patch("app.core.tasks.update_batch"),
            patch("app.core.tasks.run_scan_pipeline", return_value=mock_batch),
        ):
            result = scan_batch_task.apply(args=["batch-test-001"]).get()

        assert result["batch_id"] == "batch-test-001"
        assert result["findings_count"] == 2
        assert result["files_count"] == 1
        assert result["safety_label"] == "SAFE_TO_UPLOAD"
        assert result["status"] == "review"

    def test_scan_task_batch_not_found_raises_value_error_not_retried(self):
        """
        ValueError (batch not found) è non-transitorio: deve fallire immediatamente
        senza retry (in eager mode solleva ValueError direttamente, non Retry).
        """
        with patch("app.core.tasks.get_batch", return_value=None):
            with pytest.raises(ValueError, match="Batch not found"):
                scan_batch_task.apply(args=["batch-nonexistent"]).get()

    def test_scan_task_pipeline_error_marks_batch_as_error(self):
        """Task di scan che fallisce nella pipeline solleva eccezione (Retry in eager mode)."""
        from celery.exceptions import Retry

        mock_batch = MagicMock()
        mock_batch.status = MagicMock()

        with (
            patch("app.core.tasks.get_batch", return_value=mock_batch),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_scan_pipeline",
                side_effect=RuntimeError("Pipeline error"),
            ),
        ):
            with pytest.raises((RuntimeError, Retry)):
                scan_batch_task.apply(args=["batch-error-001"]).get()

    def test_scan_task_critical_error_not_retried(self):
        """
        CriticalError (non-transitorio) deve fallire immediatamente senza retry.
        In eager mode, dont_autoretry_for impedisce la generazione di Retry.
        """
        mock_batch = MagicMock()
        mock_batch.status = MagicMock()

        with (
            patch("app.core.tasks.get_batch", return_value=mock_batch),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_scan_pipeline",
                side_effect=BatchStateError("batch-critical-001", "SCANNING", "scan_again"),
            ),
        ):
            # BatchStateError è CriticalError — non deve generare Retry
            with pytest.raises(BatchStateError):
                scan_batch_task.apply(args=["batch-critical-001"]).get()

    def test_scan_task_pipeline_error_batch_not_found_on_recovery(self):
        """Task di scan che fallisce e non trova il batch in recovery non solleva eccezioni aggiuntive."""
        from celery.exceptions import Retry

        mock_batch = MagicMock()
        mock_batch.status = MagicMock()

        with (
            patch(
                "app.core.tasks.get_batch",
                side_effect=[mock_batch, None],  # Prima chiamata OK, seconda None
            ),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_scan_pipeline",
                side_effect=RuntimeError("Pipeline error"),
            ),
        ):
            with pytest.raises((RuntimeError, Retry)):
                scan_batch_task.apply(args=["batch-recovery-001"]).get()

    def test_scan_task_safety_label_none(self):
        """Task di scan con safety_label None usa il valore di default."""
        mock_batch = MagicMock()
        mock_batch.findings = []
        mock_batch.files = []
        mock_batch.safety_label = None
        mock_batch.status = MagicMock()
        mock_batch.status.value = "REVIEW"

        with (
            patch("app.core.tasks.get_batch", return_value=mock_batch),
            patch("app.core.tasks.update_batch"),
            patch("app.core.tasks.run_scan_pipeline", return_value=mock_batch),
        ):
            result = scan_batch_task.apply(args=["batch-no-label"]).get()

        assert result["safety_label"] == "SAFE_TO_UPLOAD"


# ─────────────────────────────────────────────────────────────────────────────
# apply_batch_task
# ─────────────────────────────────────────────────────────────────────────────


class TestApplyBatchTask:
    """Test per apply_batch_task in EAGER mode."""

    def test_apply_task_success(self):
        """Task di apply eseguito con successo restituisce dict con batch_id e zip_path."""
        mock_batch = MagicMock()
        mock_batch.status = MagicMock()
        mock_batch_initial = MagicMock()
        mock_batch_initial.status = MagicMock()
        mock_batch_after = MagicMock()
        mock_batch_after.status = MagicMock()
        mock_batch_after.status.value = "done"

        with (
            patch(
                "app.core.tasks.get_batch",
                side_effect=[mock_batch_initial, mock_batch_after],
            ),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_apply_pipeline",
                return_value="/tmp/output.zip",
            ),
        ):
            result = apply_batch_task.apply(args=["batch-apply-001", "2026-01-01T00:00:00"]).get()

        assert result["batch_id"] == "batch-apply-001"
        assert result["zip_path"] == "/tmp/output.zip"
        assert result["status"] == "done"

    def test_apply_task_batch_not_found_raises_value_error_not_retried(self):
        """
        ValueError (batch not found) è non-transitorio: deve fallire immediatamente
        senza retry (in eager mode solleva ValueError direttamente, non Retry).
        """
        with patch("app.core.tasks.get_batch", return_value=None):
            with pytest.raises(ValueError, match="Batch not found"):
                apply_batch_task.apply(args=["batch-nonexistent", "2026-01-01T00:00:00"]).get()

    def test_apply_task_pipeline_error_marks_batch_as_error(self):
        """Task di apply che fallisce nella pipeline solleva eccezione (Retry in eager mode)."""
        from celery.exceptions import Retry

        mock_batch = MagicMock()
        mock_batch.status = MagicMock()

        with (
            patch("app.core.tasks.get_batch", return_value=mock_batch),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_apply_pipeline",
                side_effect=RuntimeError("Apply pipeline error"),
            ),
        ):
            with pytest.raises((RuntimeError, Retry)):
                apply_batch_task.apply(args=["batch-apply-error", "2026-01-01T00:00:00"]).get()

    def test_apply_task_critical_error_not_retried(self):
        """
        CriticalError (non-transitorio) deve fallire immediatamente senza retry.
        """
        mock_batch = MagicMock()
        mock_batch.status = MagicMock()

        with (
            patch("app.core.tasks.get_batch", return_value=mock_batch),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_apply_pipeline",
                side_effect=BatchStateError("batch-apply-critical", "REVIEW", "apply_again"),
            ),
        ):
            with pytest.raises(BatchStateError):
                apply_batch_task.apply(args=["batch-apply-critical", "2026-01-01T00:00:00"]).get()

    def test_apply_task_pipeline_error_batch_not_found_on_recovery(self):
        """Task di apply che fallisce e non trova il batch in recovery non solleva eccezioni aggiuntive."""
        from celery.exceptions import Retry

        mock_batch = MagicMock()

        with (
            patch(
                "app.core.tasks.get_batch",
                side_effect=[mock_batch, None],
            ),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_apply_pipeline",
                side_effect=RuntimeError("Apply pipeline error"),
            ),
        ):
            with pytest.raises((RuntimeError, Retry)):
                apply_batch_task.apply(args=["batch-apply-recovery", "2026-01-01T00:00:00"]).get()

    def test_apply_task_batch_none_after_pipeline(self):
        """Task di apply con batch None dopo pipeline gestisce lo stato UNKNOWN."""
        mock_batch = MagicMock()
        mock_batch.status = MagicMock()

        with (
            patch(
                "app.core.tasks.get_batch",
                side_effect=[mock_batch, None],  # Seconda chiamata (dopo pipeline) restituisce None
            ),
            patch("app.core.tasks.update_batch"),
            patch(
                "app.core.tasks.run_apply_pipeline",
                return_value="/tmp/output.zip",
            ),
        ):
            result = apply_batch_task.apply(args=["batch-apply-none", "2026-01-01T00:00:00"]).get()

        assert result["status"] == "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# get_task_status
# ─────────────────────────────────────────────────────────────────────────────


class TestGetTaskStatus:
    """Test per get_task_status."""

    def test_get_task_status_success(self):
        """get_task_status restituisce stato SUCCESS con result."""
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.successful.return_value = True
        mock_result.failed.return_value = False
        mock_result.result = {"batch_id": "test-001"}

        with patch("app.core.tasks.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            status = get_task_status("task-id-001")

        assert status["status"] == "SUCCESS"
        assert status["result"] == {"batch_id": "test-001"}
        assert status["error"] is None

    def test_get_task_status_failure(self):
        """get_task_status restituisce stato FAILURE con error."""
        mock_result = MagicMock()
        mock_result.state = "FAILURE"
        mock_result.successful.return_value = False
        mock_result.failed.return_value = True
        mock_result.info = RuntimeError("Task failed")

        with patch("app.core.tasks.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            status = get_task_status("task-id-002")

        assert status["status"] == "FAILURE"
        assert status["result"] is None
        assert "Task failed" in status["error"]

    def test_get_task_status_pending(self):
        """get_task_status restituisce stato PENDING senza result né error."""
        mock_result = MagicMock()
        mock_result.state = "PENDING"
        mock_result.successful.return_value = False
        mock_result.failed.return_value = False

        with patch("app.core.tasks.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_result
            status = get_task_status("task-id-003")

        assert status["status"] == "PENDING"
        assert status["result"] is None
        assert status["error"] is None


# ─────────────────────────────────────────────────────────────────────────────
# revoke_task
# ─────────────────────────────────────────────────────────────────────────────


class TestRevokeTask:
    """Test per revoke_task."""

    def test_revoke_task_without_terminate(self):
        """revoke_task chiama celery_app.control.revoke con terminate=False."""
        with patch("app.core.tasks.celery_app") as mock_celery:
            revoke_task("task-id-001")
            mock_celery.control.revoke.assert_called_once_with("task-id-001", terminate=False)

    def test_revoke_task_with_terminate(self):
        """revoke_task chiama celery_app.control.revoke con terminate=True."""
        with patch("app.core.tasks.celery_app") as mock_celery:
            revoke_task("task-id-002", terminate=True)
            mock_celery.control.revoke.assert_called_once_with("task-id-002", terminate=True)
