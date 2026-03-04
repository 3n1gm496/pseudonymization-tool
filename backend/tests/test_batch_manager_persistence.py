import json
import subprocess
import sys
from pathlib import Path

import pytest
from app.core import batch_manager as bm
from app.core import batch_persistence as bp
from app.core import batch_redis as br
from app.models.schemas import Batch, BatchConfig, BatchMode, PresetName


@pytest.fixture
def isolated_batch_store(tmp_path, monkeypatch):
    with bm._global_lock:
        bm._batches.clear()
        bm._passphrases.clear()
        bm._engines.clear()
        bm._decisions.clear()
        bm._last_activity.clear()
        bm._batch_start_times.clear()
        br._redis_client_cached = None
        br._redis_last_check = 0.0
    store_dir = tmp_path / "batch-store"
    store_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bm, "TEMP_BASE_DIR", store_dir)
    monkeypatch.setattr(bp, "TEMP_BASE_DIR", store_dir)
    yield store_dir

    with bm._global_lock:
        bm._batches.clear()
        bm._passphrases.clear()
        bm._engines.clear()
        bm._decisions.clear()
        bm._last_activity.clear()
        bm._batch_start_times.clear()
        br._redis_client_cached = None
        br._redis_last_check = 0.0


def test_batch_state_visible_across_processes(isolated_batch_store):
    batch = Batch(config=BatchConfig(mode=BatchMode.STRICT, preset=PresetName.SOC_LOGS))
    batch = bm.create_batch(batch)
    bm.store_passphrase(batch.batch_id, "phase4-cross-process-passphrase")
    bm.store_decisions(
        batch.batch_id,
        [{"finding_id": "finding-1", "action": "ACCEPT", "custom_pseudonym": "A-1"}],
    )

    backend_root = Path(__file__).resolve().parents[1]
    child_script = "\n".join(
        [
            "import json",
            "import sys",
            "from pathlib import Path",
            "sys.path.insert(0, sys.argv[1])",
            "from app.core import batch_manager as bm",
            "from app.core import batch_persistence as bp",
            "bm.TEMP_BASE_DIR = Path(sys.argv[2])",
            "bp.TEMP_BASE_DIR = Path(sys.argv[2])",
            "batch_id = sys.argv[3]",
            "batch = bm.get_batch(batch_id)",
            "decisions = bm.get_decisions(batch_id)",
            "print(json.dumps({",
            "  'batch_found': bool(batch),",
            "  'status': batch.status.value if batch else None,",
            "  'passphrase': bm.get_passphrase(batch_id),",
            "  'decision_count': len(decisions),",
            "}))",
        ]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            child_script,
            str(backend_root),
            str(isolated_batch_store),
            batch.batch_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout.strip())
    assert payload["batch_found"] is True
    assert payload["status"] == "pending"
    assert payload["passphrase"] == "phase4-cross-process-passphrase"
    assert payload["decision_count"] == 1


def test_list_batches_does_not_fail_if_store_missing(monkeypatch, tmp_path):
    missing_store = tmp_path / "does-not-exist"
    monkeypatch.setattr(bm, "TEMP_BASE_DIR", missing_store)
    monkeypatch.setattr(bp, "TEMP_BASE_DIR", missing_store)

    with bm._global_lock:
        bm._batches.clear()

    assert bm.list_batches() == []


def test_batch_state_can_be_loaded_from_redis(monkeypatch, isolated_batch_store):
    class FakeRedis:
        def __init__(self):
            self._kv = {}
            self._sets = {}

        def ping(self):
            return True

        def set(self, key, value):
            self._kv[key] = value

        def get(self, key):
            return self._kv.get(key)

        def sadd(self, key, value):
            self._sets.setdefault(key, set()).add(value)

        def smembers(self, key):
            return self._sets.get(key, set())

        def delete(self, *keys):
            for key in keys:
                self._kv.pop(key, None)

        def srem(self, key, value):
            self._sets.setdefault(key, set()).discard(value)

    fake_redis = FakeRedis()
    # _get_redis_client è ora in batch_redis, non in batch_manager
    monkeypatch.setattr(br, "_get_redis_client", lambda: fake_redis)

    batch = Batch(config=BatchConfig(mode=BatchMode.STRICT, preset=PresetName.SOC_LOGS))
    created = bm.create_batch(batch)

    with bm._global_lock:
        bm._batches.pop(created.batch_id, None)

    loaded = bm.get_batch(created.batch_id)
    assert loaded is not None
    assert loaded.batch_id == created.batch_id
