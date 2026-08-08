from pathlib import Path


def test_prepare_tool_defines_one_time_vps_enrollment() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "prepare-r7425-vps-node.py").read_text()

    assert 'PROFILE_NAME = "R7425 VPS Infrastructure"' in source
    assert 'NODE_NAME = "KC-R7425-VPS-01"' in source
    assert 'purpose="vps_infrastructure"' in source
    assert 'ownership_type="khan_cloud"' in source
    assert 'visibility="internal_only"' in source
    assert "max_uses=1" in source
    assert 'print("enrollment_code: [HIDDEN INSIDE NODE INSTALLER]")' in source
    assert 'RUN_OUTPUT = Path("/tmp/khan-cloud-r7425-vps-node-install.run")' in source


def test_runtime_installer_removes_enrollment_code_after_enroll() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root
        / "node-agent"
        / "deploy"
        / "install-runtime.sh"
    ).read_text()

    assert '["deployment_enrollment_code"] = ""' in source
    assert "credentials.json" in source
    assert "systemctl enable --now khan-cloud-agent.service" in source


def test_verify_tool_requires_real_vps_inventory() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "verify-r7425-vps-node.py").read_text()

    assert '"vps_infrastructure"' in source
    assert 'docker.get("installed")' in source
    assert 'docker.get("active")' in source
    assert 'nvidia.get("available")' in source
    assert "node.gpu_count != 0" in source
    assert "heartbeat_age > 120" in source
