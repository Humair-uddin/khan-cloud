from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def _runtime() -> str:
    return (ROOT / "khan_agent/gaming_runtime.py").read_text()

def test_delete_returns_sanitization_evidence():
    s = _runtime()
    assert '"sanitization": sanitation' in s
    assert '"runtime_state_deleted": state_deleted' in s
    assert '"paired_clients_remaining": 0' in s
    assert '"recorded_launcher_alive": launcher_alive' in s

def test_idempotent_delete_proves_clean_absence():
    s = _runtime()
    assert '"idempotent": True' in s
    assert '"sanitized": True' in s
    assert '"runtime_state_deleted": True' in s

def test_cleanup_targets_only_recorded_launcher():
    s = _runtime()
    assert "def _recorded_launcher_pid" in s
    assert "def _terminate_recorded_launcher" in s
    assert '["taskkill", "/PID", str(pid), "/T", "/F"]' in s
    assert "does not enumerate or kill unrelated processes by name" in s
