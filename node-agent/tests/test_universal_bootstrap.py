from pathlib import Path

from khan_agent import inventory


def test_bootstrap_has_no_unzip_dependency():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "universal-bootstrap.sh").read_text()
    assert "unzip" not in source
    assert "base64 --decode" in source
    assert "tar -xzf -" in source


def test_bootstrap_auto_remediates_python_venv_only_as_safe_prerequisite():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "universal-bootstrap.sh").read_text()
    assert "safe_apt_install python3-venv" in source
    assert "safe_apt_install ca-certificates" in source
    assert "nvidia" not in source.lower()
    assert "docker" not in source.lower()
    assert "partition" not in source.lower()


def test_runtime_is_checkpointed_and_enrollment_is_idempotent():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "install-runtime.sh").read_text()
    assert "install-runtime.checkpoints" in source
    assert 'if [[ -s "$STATE/credentials.json" ]]' in source
    assert "enrollment checkpoint recovered" in source
    assert "mark_done enrolled" in source
    assert "mark_done heartbeat_verified" in source
    assert "mark_done completed" in source


def test_builder_creates_self_extracting_run_without_external_zip(tmp_path):
    import subprocess
    root = Path(__file__).resolve().parents[1]
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "install.sh").write_text("#!/bin/sh\nexit 0\n")
    output = tmp_path / "node.run"
    subprocess.run(
        [
            "python3",
            str(root / "deploy" / "build-universal-run.py"),
            "--bootstrap", str(root / "deploy" / "universal-bootstrap.sh"),
            "--payload", str(payload),
            "--output", str(output),
        ],
        check=True,
    )
    data = output.read_text(errors="ignore")
    assert "__KC_PAYLOAD_BELOW__" in data
    assert output.stat().st_mode & 0o111
