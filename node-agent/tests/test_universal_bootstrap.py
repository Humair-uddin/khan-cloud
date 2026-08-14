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


def test_runtime_installer_has_role_aware_gaming_service_policy():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "install-runtime.sh").read_text()

    assert 'NODE_ROLE=' in source
    assert 'if [[ "$NODE_ROLE" == "gaming_host" ]]' in source
    assert "SupplementaryGroups=kvm libvirt" in source
    assert "SupplementaryGroups=kvm" in source
    assert "/var/lib/khan-cloud/vps" in source
    assert "ReadWritePaths=/var/lib/khan-cloud-agent" in source


def test_default_systemd_template_retains_vps_requirements():
    root = Path(__file__).resolve().parents[1]
    source = (root / "systemd" / "khan-cloud-agent.service").read_text()

    assert "SupplementaryGroups=kvm libvirt" in source
    assert (
        "ReadWritePaths=/var/lib/khan-cloud-agent /var/lib/khan-cloud/vps"
        in source
    )


def test_runtime_update_preserves_existing_node_identity():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.sh").read_text()

    assert 'test -f "$STATE/credentials.json"' in source
    assert '"$STATE/credentials.json"' in source
    assert "--enroll" not in source
    assert "credentials.json" not in source.split('echo "===== UPDATE RUNTIME ====="')[1].split(
        'echo "===== UPDATE CONFIG ====="'
    )[0]


def test_runtime_update_has_backup_validation_and_heartbeat():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.sh").read_text()

    assert 'tar -czf "$BACKUP"' in source
    assert 'python" -m compileall' in source
    assert 'python" -m pytest -q' in source
    assert 'systemctl start "$SERVICE"' in source
    assert "--heartbeat-once" in source


def test_runtime_update_replaces_agent_code_not_whole_state():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.sh").read_text()

    assert '"$RUNTIME/khan_agent"' in source
    assert '"$RUNTIME/deploy"' in source
    assert '"$RUNTIME/tests"' in source
    assert 'cp -a "$SOURCE_DIR/khan_agent" "$RUNTIME/khan_agent"' in source
    assert 'cp -a "$SOURCE_DIR/deploy" "$RUNTIME/deploy"' in source
    assert 'cp -a "$SOURCE_DIR/tests" "$RUNTIME/tests"' in source
    assert 'rm -rf "$STATE"' not in source
    assert 'rm -f "$STATE/credentials.json"' not in source


def test_runtime_update_deploys_matching_runtime_components():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.sh").read_text()

    assert "for component in khan_agent deploy tests" in source
    assert 'cp -a "$SOURCE_DIR/khan_agent" "$RUNTIME/khan_agent"' in source
    assert 'cp -a "$SOURCE_DIR/deploy" "$RUNTIME/deploy"' in source
    assert 'cp -a "$SOURCE_DIR/tests" "$RUNTIME/tests"' in source


def test_windows_runtime_updater_exists():
    root = Path(__file__).resolve().parents[1]
    updater = root / "deploy" / "apply-runtime-update.ps1"

    assert updater.is_file()


def test_windows_runtime_update_preserves_existing_node_identity():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.ps1").read_text()

    assert "credentials.json" in source
    assert "identity.json" in source
    assert "--enroll" not in source


def test_windows_runtime_update_uses_programdata_agent_state():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.ps1").read_text()

    assert "ProgramData" in source
    assert "KhanCloud" in source
    assert "Agent" in source


def test_windows_runtime_update_deploys_matching_runtime_components():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.ps1").read_text()

    assert "khan_agent" in source
    assert "deploy" in source
    assert "tests" in source


def test_windows_runtime_update_validates_runtime_before_restart():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.ps1").read_text()

    assert "compileall" in source
    assert "pytest" in source


def test_windows_runtime_update_verifies_heartbeat():
    root = Path(__file__).resolve().parents[1]
    source = (root / "deploy" / "apply-runtime-update.ps1").read_text()

    assert "--heartbeat-once" in source
