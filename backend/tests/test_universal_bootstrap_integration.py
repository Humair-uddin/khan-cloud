from pathlib import Path


def test_r7425_runtime_installer_uses_universal_safe_prerequisites():
    root = Path(__file__).resolve().parents[2]
    source = (root / "node-agent" / "deploy" / "install-runtime.sh").read_text()
    assert "ensure_python_venv" in source
    assert "safe_apt_install python3-venv" in source
    assert "CHECKPOINTS=" in source


def test_universal_bootstrap_is_self_extracting_and_resumable():
    root = Path(__file__).resolve().parents[2]
    source = (root / "node-agent" / "deploy" / "universal-bootstrap.sh").read_text()
    assert "bootstrap.checkpoints" in source
    assert "payload_extracted" in source
    assert "installer_completed" in source
    assert "SUCCESS: KHAN CLOUD UNIVERSAL NODE BOOTSTRAP COMPLETE" in source
