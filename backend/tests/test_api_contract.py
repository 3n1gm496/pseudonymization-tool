import io

from fastapi.testclient import TestClient

from app.main import app
from app.api import routes
from app.models.schemas import SafetyLabel


client = TestClient(app)


def test_health_and_ready_contract():
    health = client.get('/api/health')
    assert health.status_code == 200
    health_data = health.json()
    assert 'status' in health_data
    assert 'service' in health_data
    assert 'version' in health_data

    ready = client.get('/api/ready')
    assert ready.status_code == 200
    ready_data = ready.json()
    assert 'ready' in ready_data
    assert 'checks' in ready_data


def test_policy_preview_contract():
    presets = client.get('/api/settings/policies')
    assert presets.status_code == 200
    assert 'presets' in presets.json()

    preview = client.get('/api/settings/policies/SOC%20Logs')
    assert preview.status_code == 200
    body = preview.json()
    assert body['preset'] == 'SOC Logs'
    assert 'enabled_entity_types' in body
    assert 'confidence_threshold' in body


def test_console_scan_contract(monkeypatch):
    def fake_run_text_scan(batch_id: str, text: str, label: str):
        return 'file-contract-1', [], SafetyLabel.SAFE_TO_UPLOAD

    monkeypatch.setattr(routes, 'run_text_scan', fake_run_text_scan)

    response = client.post('/api/console/scan', json={
        'text': 'email: test@example.com',
        'mode': 'light',
        'preset': 'SOC Logs',
    })

    assert response.status_code == 200
    data = response.json()
    assert 'batch_id' in data
    assert 'file_id' in data
    assert 'passphrase' in data
    assert 'findings' in data
    assert 'safety_label' in data


def test_console_apply_contract(monkeypatch):
    def fake_run_text_scan(batch_id: str, text: str, label: str):
        return 'file-contract-2', [], SafetyLabel.SAFE_TO_UPLOAD

    def fake_run_text_apply(batch_id: str, file_id: str, original_text: str):
        return 'masked text', SafetyLabel.SAFE_TO_UPLOAD, [], 1

    monkeypatch.setattr(routes, 'run_text_scan', fake_run_text_scan)
    monkeypatch.setattr(routes, 'run_text_apply', fake_run_text_apply)

    scan = client.post('/api/console/scan', json={
        'text': 'user@example.com',
        'mode': 'light',
        'preset': 'SOC Logs',
    })
    assert scan.status_code == 200
    scan_data = scan.json()

    apply_resp = client.post('/api/console/apply', json={
        'batch_id': scan_data['batch_id'],
        'file_id': scan_data['file_id'],
        'text': 'user@example.com',
    })

    assert apply_resp.status_code == 200
    apply_data = apply_resp.json()
    assert apply_data['batch_id'] == scan_data['batch_id']
    assert 'pseudonymized_text' in apply_data
    assert 'safety_label' in apply_data
    assert 'applied_count' in apply_data


def test_batch_create_contract(monkeypatch):
    monkeypatch.setattr(routes, 'run_scan_pipeline', lambda batch_id: routes.get_batch(batch_id))

    file_content = io.BytesIO(b'Utente: alice@example.com')
    response = client.post(
        '/api/batches',
        data={
            'mode': 'light',
            'preset': 'SOC Logs',
            'passphrase': 'Str0ng!Passphrase#2026X',
        },
        files={'files': ('contract.txt', file_content, 'text/plain')},
    )

    assert response.status_code == 200
    body = response.json()
    assert 'batch_id' in body
    assert 'status' in body
    assert 'files' in body
    assert 'findings_count' in body
