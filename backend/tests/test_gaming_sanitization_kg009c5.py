from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def _read(p: str) -> str:
    return (ROOT / p).read_text()

def test_delete_requires_sanitization_proof_before_repool():
    s = _read("app/services/gaming_service.py")
    assert "proof_ok" in s
    assert "runtime_sanitization_unproven" in s
    assert 'session.status = "quarantined"' in s
    assert "node_sanitization_proof_missing_or_failed" in s

def test_sanitization_fields_are_persisted():
    s = _read("app/models/compute.py")
    for name in ("sanitization_state", "sanitization_attempt_count", "sanitization_last_checked_at", "sanitized_at", "quarantine_reason"):
        assert name in s

def test_migration_follows_c4():
    s = _read("migrations/versions/c5a009f10001_gaming_runtime_sanitization_v1.py")
    assert 'revision = "c5a009f10001"' in s
    assert 'down_revision = "c4a009f10001"' in s
