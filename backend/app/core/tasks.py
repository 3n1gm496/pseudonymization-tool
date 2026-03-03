"""
Celery Task Definitions - Phase 4 Async Architecture
Handles long-running scan and apply operations asynchronously.

Tasks:
- scan_batch_task: Async file batch scanning (parsing, detection, findings)
- apply_batch_task: Async batch transformation (outputs, report, mapping generation)

Configuration:
- Broker: Redis (via CELERY_BROKER_URL)
- Backend: Redis (via CELERY_RESULT_BACKEND)
- Worker: Single concurrency on single VM (scale horizontally if needed)

Retry policy:
- Only transient errors are retried (RecoverableError subclasses, IOError, OSError,
  MemoryError, TimeoutError).
- Non-transient errors (CriticalError subclasses, ValueError, TypeError, etc.) are
  NOT retried: they indicate a programming error or an invalid state that will not
  resolve itself on retry.

Usage in endpoints:
  from app.core.tasks import scan_batch_task, apply_batch_task

  # Enqueue scan task (non-blocking)
  task = scan_batch_task.delay(batch_id)

  # Poll task status
  task.status  # 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE'
"""

import logging
import os

from app.core.batch_manager import get_batch, update_batch
from app.core.exceptions import CriticalError, RecoverableError
from app.core.pipeline import run_apply_pipeline, run_scan_pipeline
from app.models.schemas import BatchStatus
from celery import Celery, Task

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Celery App Configuration
# ─────────────────────────────────────────────────────────────────────────────

celery_app = Celery(
    "pseudonymization_tool",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution timeouts (more generous than HTTP timeouts)
    task_soft_time_limit=1200,  # 20 minutes soft limit
    task_time_limit=1500,  # 25 minutes hard limit
    # Worker configuration for single VM
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_max_tasks_per_child=1000,  # Refresh worker process periodically
    # Auto-scale disabled on single VM
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "1")),
    # Enable result cleanup after completion
    result_expires=3600,  # Keep results for 1 hour
    # Task routing (both tasks to same queue)
    task_routes={
        "app.core.tasks.scan_batch_task": {"queue": "pseudonymization"},
        "app.core.tasks.apply_batch_task": {"queue": "pseudonymization"},
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Non-transient exception types — never retried
# ─────────────────────────────────────────────────────────────────────────────

#: Tuple of exception types that are considered non-transient and must NOT be
#: retried by Celery.  These represent programming errors, invalid state, or
#: configuration problems that will not resolve themselves on a subsequent
#: attempt.  Retrying them would waste resources and potentially corrupt state.
NON_RETRYABLE_EXCEPTIONS = (
    CriticalError,   # BatchStateError, CryptoError, PipelineError, BatchError, ConfigError …
    ValueError,      # Raised explicitly for "Batch not found" guard clauses
    TypeError,       # Programming errors
    KeyError,        # Missing required keys — programming error
    AttributeError,  # Programming errors
)


# ─────────────────────────────────────────────────────────────────────────────
# Custom Task Class with Database Context Handling
# ─────────────────────────────────────────────────────────────────────────────


class DatabaseTask(Task):
    """
    Custom task class for proper error handling and state management.
    Ensures batch state is updated throughout task lifecycle.

    Retry policy:
    - Transient errors (RecoverableError, IOError, OSError, MemoryError,
      TimeoutError) are retried up to 3 times with exponential backoff.
    - Non-transient errors (NON_RETRYABLE_EXCEPTIONS) are NOT retried.
      They fail immediately and mark the batch as ERROR.
    """

    # Only retry on transient/recoverable errors.
    # RecoverableError covers: ParsingError, DetectionError, TransformError,
    # PolicyError, SafetyCheckError and all their subclasses.
    autoretry_for = (RecoverableError, IOError, OSError, MemoryError, TimeoutError)
    # Explicitly exclude non-transient errors from retry.
    dont_autoretry_for = NON_RETRYABLE_EXCEPTIONS
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_max = 60


# ─────────────────────────────────────────────────────────────────────────────
# TASK 1: Async Scan Pipeline
# ─────────────────────────────────────────────────────────────────────────────


@celery_app.task(base=DatabaseTask, bind=True, name="app.core.tasks.scan_batch_task")
def scan_batch_task(self, batch_id: str) -> dict:
    """
    Async scan task: Parse files, detect entities, populate findings.

    Args:
        batch_id: Unique batch identifier

    Returns:
        dict with:
        - batch_id: The processed batch ID
        - findings_count: Number of findings detected
        - files_count: Number of files processed
        - safety_label: Overall safety assessment
        - status: Final batch status

    Raises:
        ValueError: If batch not found (non-transient, not retried)
        CriticalError: If batch is in an invalid state (non-transient, not retried)
        RecoverableError: Transient parsing/detection errors (auto-retried up to 3x)
    """
    try:
        logger.info("Scan task starting for batch: %s", batch_id)

        # Verify batch exists — ValueError is non-transient, will not be retried
        batch = get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch not found: {batch_id}")

        # Mark as scanning
        batch.status = BatchStatus.SCANNING
        update_batch(batch)

        # Run scanning pipeline (blocking, CPU-intensive)
        batch = run_scan_pipeline(batch_id)

        # Mark as ready for review
        batch.status = BatchStatus.REVIEW
        update_batch(batch)

        logger.info(
            "Scan task completed for batch %s: %d findings in %d files",
            batch_id,
            len(batch.findings),
            len(batch.files),
        )

        return {
            "batch_id": batch_id,
            "findings_count": len(batch.findings),
            "files_count": len(batch.files),
            "safety_label": batch.safety_label.value if batch.safety_label else "SAFE_TO_UPLOAD",
            "status": batch.status.value,
        }

    except Exception as exc:
        logger.error("Scan task failed for batch %s: %s", batch_id, exc, exc_info=True)

        # Mark batch as error (best-effort — do not raise if batch is gone)
        batch = get_batch(batch_id)
        if batch:
            batch.status = BatchStatus.ERROR
            batch.error_message = str(exc)
            update_batch(batch)

        # Re-raise to trigger retry (for transient errors) or final failure
        raise


# ─────────────────────────────────────────────────────────────────────────────
# TASK 2: Async Apply Pipeline
# ─────────────────────────────────────────────────────────────────────────────


@celery_app.task(base=DatabaseTask, bind=True, name="app.core.tasks.apply_batch_task")
def apply_batch_task(self, batch_id: str, started_at: str) -> dict:
    """
    Async apply task: Transform files, generate mapping, create output ZIP.

    Prerequisites:
    - Batch must be in REVIEW status
    - User decisions must be stored in batch state
    - Passphrase must be available

    Args:
        batch_id: Unique batch identifier
        started_at: ISO timestamp of scan start (for audit)

    Returns:
        dict with:
        - batch_id: The processed batch ID
        - zip_path: Path to output ZIP file
        - decisions_count: Number of review decisions applied
        - status: Final batch status

    Raises:
        ValueError: If batch not found (non-transient, not retried)
        CriticalError: If batch is in an invalid state (non-transient, not retried)
        TransformError: Transient file processing errors (auto-retried up to 3x)
    """
    try:
        logger.info("Apply task starting for batch: %s", batch_id)

        # Verify batch exists — ValueError is non-transient, will not be retried
        batch = get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch not found: {batch_id}")

        # Mark as applying
        batch.status = BatchStatus.APPLYING
        update_batch(batch)

        # Run apply pipeline (blocking, file I/O intensive)
        zip_path = run_apply_pipeline(batch_id, started_at)

        # Pipeline sets status to DONE or DONE_WITH_ERRORS
        batch = get_batch(batch_id)

        logger.info(
            "Apply task completed for batch %s: output at %s",
            batch_id,
            zip_path,
        )

        return {
            "batch_id": batch_id,
            "zip_path": str(zip_path),
            "status": batch.status.value if batch else "UNKNOWN",
        }

    except Exception as exc:
        logger.error("Apply task failed for batch %s: %s", batch_id, exc, exc_info=True)

        # Mark batch as error (best-effort — do not raise if batch is gone)
        batch = get_batch(batch_id)
        if batch:
            batch.status = BatchStatus.ERROR
            batch.error_message = str(exc)
            update_batch(batch)

        # Re-raise to trigger retry (for transient errors) or final failure
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Task Management Utilities
# ─────────────────────────────────────────────────────────────────────────────


def get_task_status(task_id: str) -> dict:
    """
    Get current status of a Celery task.

    Args:
        task_id: Celery task ID

    Returns:
        dict with:
        - status: Task state (PENDING, STARTED, SUCCESS, FAILURE, RETRY)
        - result: Task result if completed
        - error: Error message if failed
    """
    result = celery_app.AsyncResult(task_id)
    return {
        "status": result.state,
        "result": result.result if result.successful() else None,
        "error": str(result.info) if result.failed() else None,
    }


def revoke_task(task_id: str, terminate: bool = False) -> None:
    """
    Revoke (cancel) a pending or running task.

    Args:
        task_id: Celery task ID
        terminate: If True, terminate running task immediately
    """
    celery_app.control.revoke(task_id, terminate=terminate)
    logger.info("Task %s revoked (terminate=%s)", task_id, terminate)
