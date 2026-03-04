"""
Test per l'endpoint SSE GET /api/batches/{batch_id}/events.
Verifica il generatore di eventi, i casi terminali e il comportamento
con batch non trovati.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from app.api.batches_routes import _sse_batch_event_generator
from app.models.schemas import Batch, BatchConfig, BatchMode, BatchStatus, PresetName
from fastapi.testclient import TestClient

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_batch(status: BatchStatus, task_id: str | None = None, error: str | None = None) -> Batch:
    b = Batch(config=BatchConfig(mode=BatchMode.STRICT, preset=PresetName.SOC_LOGS))
    b.status = status
    b.task_id = task_id
    b.error_message = error
    return b


async def _collect_events(
    batch_id: str,
    get_batch_side_effect,
    get_task_status_side_effect=None,
    timeout_seconds: int = 10,
    poll_interval: float = 0.01,
) -> list[dict]:
    """Raccoglie tutti gli eventi SSE dal generatore."""
    events = []
    with (
        patch("app.api.batches_routes.get_batch", side_effect=get_batch_side_effect),
        patch(
            "app.api.batches_routes.get_task_status",
            side_effect=get_task_status_side_effect or (lambda _: {"status": "SUCCESS"}),
        ),
    ):
        async for raw in _sse_batch_event_generator(
            batch_id,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        ):
            # Estrai solo le righe "data: ..."
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
    return events


# ─── Test: evento iniziale di connessione ─────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_first_event_is_connected():
    """Il primo evento deve essere {type: 'connected', batch_id: ...}."""
    batch = _make_batch(BatchStatus.DONE)
    events = await _collect_events(
        "batch-001",
        get_batch_side_effect=[batch],
    )
    assert events[0]["type"] == "connected"
    assert events[0]["batch_id"] == "batch-001"


# ─── Test: stato terminale 'done' ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_terminates_on_done():
    """Il generatore deve terminare quando lo stato è 'done'."""
    batch = _make_batch(BatchStatus.DONE)
    events = await _collect_events(
        "batch-done",
        get_batch_side_effect=[batch, batch],
    )
    status_events = [e for e in events if e.get("type") == "status"]
    assert any(e["status"] == "done" for e in status_events)


# ─── Test: stato terminale 'done_with_errors' ─────────────────────────────────


@pytest.mark.asyncio
async def test_sse_terminates_on_done_with_errors():
    """Il generatore deve terminare quando lo stato è 'done_with_errors'."""
    batch = _make_batch(BatchStatus.DONE_WITH_ERRORS)
    events = await _collect_events(
        "batch-dwe",
        get_batch_side_effect=[batch, batch],
    )
    status_events = [e for e in events if e.get("type") == "status"]
    assert any(e["status"] == "done_with_errors" for e in status_events)


# ─── Test: stato terminale 'error' ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_terminates_on_error():
    """Il generatore deve terminare quando lo stato è 'error'."""
    batch = _make_batch(BatchStatus.SCANNING, task_id="task-err", error="Errore grave")

    def task_status_failure(_):
        return {"status": "FAILURE", "error": "Errore grave"}

    events = await _collect_events(
        "batch-err",
        get_batch_side_effect=[batch, batch],
        get_task_status_side_effect=task_status_failure,
    )
    status_events = [e for e in events if e.get("type") == "status"]
    assert any(e["status"] == "error" for e in status_events)


# ─── Test: batch non trovato ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_batch_not_found():
    """Se il batch non esiste, deve emettere un evento {type: 'error'}."""
    events = await _collect_events(
        "batch-missing",
        get_batch_side_effect=[None],
    )
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["batch_id"] == "batch-missing"


# ─── Test: nessun evento duplicato se lo stato non cambia ─────────────────────


@pytest.mark.asyncio
async def test_sse_no_duplicate_status_events():
    """Non deve emettere eventi duplicati se lo stato non cambia."""
    batch_scanning = _make_batch(BatchStatus.SCANNING, task_id="task-1")
    batch_done = _make_batch(BatchStatus.DONE, task_id="task-1")

    call_count = 0

    def get_batch_seq(_):
        nonlocal call_count
        call_count += 1
        # Prima 3 chiamate: scanning; poi: done
        if call_count <= 3:
            return batch_scanning
        return batch_done

    def task_status_started(_):
        if call_count <= 3:
            return {"status": "STARTED"}
        return {"status": "SUCCESS"}

    events = await _collect_events(
        "batch-nodup",
        get_batch_side_effect=get_batch_seq,
        get_task_status_side_effect=task_status_started,
    )
    status_events = [e for e in events if e.get("type") == "status"]
    # Ogni status deve apparire al massimo una volta
    statuses = [e["status"] for e in status_events]
    assert len(statuses) == len(set(statuses)), f"Status duplicati: {statuses}"


# ─── Test: transizione pending → running → done ───────────────────────────────


@pytest.mark.asyncio
async def test_sse_status_transitions():
    """Verifica la transizione pending → running → done."""
    batch = _make_batch(BatchStatus.SCANNING, task_id="task-trans")

    call_count = 0

    def task_status_seq(_):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"status": "PENDING"}
        elif call_count == 2:
            return {"status": "STARTED"}
        else:
            return {"status": "SUCCESS"}

    def get_batch_seq(_):
        if call_count >= 3:
            b = _make_batch(BatchStatus.DONE, task_id="task-trans")
        else:
            b = _make_batch(BatchStatus.SCANNING, task_id="task-trans")
        return b

    events = await _collect_events(
        "batch-trans",
        get_batch_side_effect=get_batch_seq,
        get_task_status_side_effect=task_status_seq,
    )
    status_events = [e for e in events if e.get("type") == "status"]
    statuses = [e["status"] for e in status_events]
    assert "pending" in statuses
    assert "running" in statuses
    assert "done" in statuses


# ─── Test: endpoint HTTP GET /api/batches/{id}/events ─────────────────────────


@pytest.fixture
def client():
    """TestClient con autenticazione disabilitata (gestita dal conftest)."""
    from app.main import app

    return TestClient(app)


def test_sse_endpoint_404_for_missing_batch(client: TestClient):
    """L'endpoint deve restituire 404 se il batch non esiste."""
    with patch("app.api.batches_routes.get_batch", return_value=None):
        response = client.get("/api/batches/nonexistent/events")
    assert response.status_code == 404


def test_sse_endpoint_returns_event_stream_content_type(client: TestClient):
    """L'endpoint deve restituire Content-Type text/event-stream."""
    batch = _make_batch(BatchStatus.DONE)

    with (
        patch("app.api.batches_routes.get_batch", return_value=batch),
        patch("app.api.batches_routes.get_task_status", return_value={"status": "SUCCESS"}),
    ):
        # Usa stream=True per non consumare tutto il body
        with client.stream("GET", f"/api/batches/{batch.batch_id}/events") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")


def test_sse_endpoint_cache_control_header(client: TestClient):
    """L'endpoint deve avere Cache-Control: no-cache."""
    batch = _make_batch(BatchStatus.DONE)

    with (
        patch("app.api.batches_routes.get_batch", return_value=batch),
        patch("app.api.batches_routes.get_task_status", return_value={"status": "SUCCESS"}),
    ):
        with client.stream("GET", f"/api/batches/{batch.batch_id}/events") as response:
            assert response.headers.get("cache-control") == "no-cache"
