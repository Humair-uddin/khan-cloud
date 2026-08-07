from pathlib import Path


def test_backend_env_path_is_absolute_and_stable() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "core" / "config.py").read_text()

    assert "BACKEND_ROOT = Path(__file__).resolve().parents[2]" in source
    assert 'ENV_FILE = BACKEND_ROOT / ".env"' in source
    assert "env_file=str(ENV_FILE)" in source


def test_control_plane_systemd_unit_uses_existing_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    unit = (
        root
        / "deploy"
        / "systemd"
        / "khan-cloud-control-plane.service"
    ).read_text()

    assert "User=khanadmin" in unit
    assert "WorkingDirectory=/opt/khan-cloud/source/backend" in unit
    assert (
        "ExecStart=/opt/khan-cloud/source/backend/.venv/bin/python "
        "-m uvicorn app.main:app"
    ) in unit
    assert "EnvironmentFile=/opt/khan-cloud/source/backend/.env" in unit
    assert "Restart=on-failure" in unit
    assert "NoNewPrivileges=true" in unit
    assert "CapabilityBoundingSet=" in unit


def test_runtime_status_script_checks_all_live_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "control-plane-status.sh").read_text()

    assert "/health" in script
    assert "/ready" in script
    assert "/version" in script
    assert "/ui/" in script
