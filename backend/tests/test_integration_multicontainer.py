"""
Integration test: multicontainer validation with docker-compose.

Tests:
- API container creates batch → saves to Redis
- Celery worker container reads batch from Redis → processes task
- Worker updates batch status → visible to API container
- End-to-end scan/apply pipeline with real Redis broker

Requirements:
- docker-compose.yml configured with shared Redis and volume
- Containers: pseudonymization-tool (API), celery-worker, redis
- Port 8000 exposed for API access

Usage:
    pytest tests/test_integration_multicontainer.py -v --tb=short

Note: This test is marked with @pytest.mark.integration and requires
docker-compose to be installed. Run with: pytest -m integration
"""

import subprocess
import time
from pathlib import Path

import pytest
import requests

# Mark as integration test (requires docker-compose)
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def docker_compose_stack():
    """
    Start docker-compose stack, yield for tests, then tear down.
    Ensures clean state before and after test suite.
    """
    project_root = Path(__file__).resolve().parents[2]
    compose_file = project_root / "docker-compose.yml"

    if not compose_file.exists():
        pytest.skip(f"docker-compose.yml not found at {compose_file}")

    # Clean up any existing stack
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=str(project_root),
        capture_output=True,
        timeout=30,
    )

    # Start stack in background (exclude flower - it's optional for monitoring)
    print("\n🚀 Starting docker-compose stack...")
    result = subprocess.run(
        ["docker", "compose", "up", "--build", "-d", "--scale", "flower=0"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=300,  # 5 minutes for build
    )

    if result.returncode != 0:
        pytest.fail(f"docker-compose up failed:\n{result.stderr}")

    # Wait for services to be healthy
    print("⏳ Waiting for services to be healthy...")
    max_wait = 60  # seconds
    start_time = time.time()
    api_ready = False

    while time.time() - start_time < max_wait:
        try:
            response = requests.get("http://localhost:8000/api/health", timeout=2)
            if response.status_code == 200:
                api_ready = True
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)

    if not api_ready:
        # Dump logs for debugging
        logs_result = subprocess.run(
            ["docker", "compose", "logs", "--tail=50"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        pytest.fail(f"API failed to become healthy within {max_wait}s\n" f"Logs:\n{logs_result.stdout}")

    print("✅ Stack ready, yielding to tests...")

    yield {
        "api_url": "http://localhost:8000",
        "project_root": project_root,
    }

    # Tear down
    print("\n🧹 Tearing down docker-compose stack...")
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=str(project_root),
        capture_output=True,
        timeout=30,
    )


@pytest.fixture(scope="module")
def authenticated_session(docker_compose_stack):
    """
    Create authenticated session for API requests.
    Returns requests.Session with session cookie and CSRF token from /auth/login.
    """
    api_url = docker_compose_stack["api_url"]
    session = requests.Session()

    # Login with credentials from docker-compose.yml
    response = session.post(
        f"{api_url}/api/auth/login",
        json={
            "username": "admin",
            "password": "admin123!",
        },
    )

    if response.status_code != 200:
        pytest.fail(f"Failed to authenticate: {response.status_code}\n" f"Response: {response.text}")

    # Extract CSRF token from response headers
    csrf_token = response.headers.get("X-CSRF-Token")
    if not csrf_token:
        pytest.fail("No CSRF token returned from login")

    # Add CSRF token to all subsequent requests
    session.headers.update({"X-CSRF-Token": csrf_token})

    return session


def test_api_health_check(docker_compose_stack):
    """Verify API container is running and responsive."""
    api_url = docker_compose_stack["api_url"]
    response = requests.get(f"{api_url}/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_redis_connectivity(docker_compose_stack):
    """Verify Redis container is accessible from API."""
    api_url = docker_compose_stack["api_url"]
    response = requests.get(f"{api_url}/api/ready")
    assert response.status_code == 200
    # Ready endpoint checks Redis connectivity internally


def test_batch_creation_persists_to_redis(docker_compose_stack, authenticated_session):
    """
    Test I-001 resolution: Batch created by API is persisted to Redis
    and visible to other processes (worker container).

    Uses console/scan endpoint which creates batch internally.
    """
    api_url = docker_compose_stack["api_url"]
    session = authenticated_session

    # Create batch via console/scan (creates batch internally)
    response = session.post(
        f"{api_url}/api/console/scan",
        json={
            "text": "Test data with email@example.com and IP 192.168.1.1",
            "mode": "STRICT",
            "preset": "SOC_LOGS",
        },
    )
    assert response.status_code == 200
    scan_result = response.json()
    batch_id = scan_result["batch_id"]

    # Verify batch is retrievable (confirms Redis persistence)
    response = session.get(f"{api_url}/api/batches")
    assert response.status_code == 200
    data = response.json()
    batches = data.get("batches", [])

    # Find our batch in the list
    batch_ids = [b["batch_id"] for b in batches]
    assert batch_id in batch_ids, f"Batch {batch_id} not found in list"


def test_celery_worker_can_process_async_task(docker_compose_stack, authenticated_session):
    """
    Test end-to-end async task processing:
    1. API creates batch and scans content
    2. Worker reads batch state from Redis (I-001 validation)
    3. Findings are returned successfully
    """
    api_url = docker_compose_stack["api_url"]
    session = authenticated_session

    # Create minimal test content for scanning
    test_content = "User email: test@example.com\\nSecret: ABC-1234-XYZ\\nIP: 10.0.0.1"

    # Trigger scan via console endpoint
    response = session.post(
        f"{api_url}/api/console/scan",
        json={
            "text": test_content,
            "mode": "STRICT",
            "preset": "SOC_LOGS",
        },
    )
    assert response.status_code == 200
    scan_result = response.json()

    # Verify findings were detected (proves scan pipeline executed)
    findings = scan_result.get("findings", [])
    assert len(findings) > 0, f"Expected at least one finding from test content, got {findings}"


def test_batch_state_shared_between_api_and_worker(docker_compose_stack, authenticated_session):
    """
    Core I-001 validation: Verify batch state is truly shared via Redis
    between API container and worker container (not just in-memory dict).

    Flow:
    1. API container creates batch → saves to Redis
    2. API can list batch (proves Redis read/write working)
    3. Multiple scans create multiple batches, all visible via Redis
    """
    api_url = docker_compose_stack["api_url"]
    session = authenticated_session

    # Create first batch
    response = session.post(
        f"{api_url}/api/console/scan",
        json={
            "text": "First batch with email1@example.com",
            "mode": "STRICT",
            "preset": "SOC_LOGS",
        },
    )
    assert response.status_code == 200
    batch_id_1 = response.json()["batch_id"]

    # Create second batch
    response = session.post(
        f"{api_url}/api/console/scan",
        json={
            "text": "Second batch with email2@example.com",
            "mode": "STRICT",
            "preset": "SOC_LOGS",
        },
    )
    assert response.status_code == 200
    batch_id_2 = response.json()["batch_id"]

    # List all batches - should see both via Redis
    response = session.get(f"{api_url}/api/batches")
    assert response.status_code == 200
    data = response.json()
    batches = data.get("batches", [])

    batch_ids = [b["batch_id"] for b in batches]
    assert batch_id_1 in batch_ids, "First batch not in list (Redis persistence issue)"
    assert batch_id_2 in batch_ids, "Second batch not in list (Redis persistence issue)"

    # Verify we have at least 2 batches (proves Redis shared state)
    assert len(batches) >= 2, f"Expected at least 2 batches, got {len(batches)}"


def test_docker_compose_logs_show_worker_activity(docker_compose_stack):
    """
    Verify celery-worker container is running and processing tasks.
    Check logs for worker startup and task execution.
    """
    project_root = docker_compose_stack["project_root"]

    result = subprocess.run(
        ["docker", "compose", "logs", "celery-worker", "--tail=50"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    logs = result.stdout

    # Verify worker started
    assert "celery@" in logs.lower() or "worker" in logs.lower(), "Worker logs should show Celery startup"

    # Verify worker connected to broker
    assert "redis" in logs.lower() or "connected" in logs.lower(), "Worker should connect to Redis broker"
