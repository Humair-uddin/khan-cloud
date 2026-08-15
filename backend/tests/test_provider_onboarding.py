from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.provider_onboarding_service import (
    ProviderOnboardingError,
    _profile_settings_for_role,
    hash_download_token,
)


def user(*roles, superuser=False):
    return SimpleNamespace(is_superuser=superuser, roles=[SimpleNamespace(name=r, permissions=[]) for r in roles])


def test_download_token_is_hashed_not_stored_plaintext():
    token = "kcinst_example-secret"
    digest = hash_download_token(token)
    assert token not in digest
    assert len(digest) == 64


def test_operator_can_generate_vps_host_profile():
    settings = _profile_settings_for_role(user("operator"), "vps_host")
    assert settings["purpose"] == "vps_infrastructure"
    assert settings["resource_policy"]["auto_approve_node"] is True


def test_customer_cannot_generate_khan_cloud_vps_infrastructure():
    with pytest.raises(ProviderOnboardingError):
        _profile_settings_for_role(user("customer"), "vps_host")


def test_customer_can_generate_private_compute_installer():
    settings = _profile_settings_for_role(user("customer"), "private_compute")
    assert settings["purpose"] == "organization_private"
    assert settings["ownership_type"] == "organization"
    assert settings["resource_policy"]["auto_approve_node"] is True


def test_provider_api_and_frontend_are_wired():
    root = Path(__file__).resolve().parents[1]
    api = (root / "app" / "api" / "v1" / "provider.py").read_text()
    main = (root / "app" / "main.py").read_text()
    assert '"/node-installers"' in api
    assert '"/bootstrap/{token}"' in api
    assert "provider_router" in main


def test_installer_generation_uses_universal_run_builder():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "services" / "provider_onboarding_service.py").read_text()
    assert "build-universal-run.py" in source
    assert "universal-bootstrap.sh" in source
    assert "deployment_enrollment_code" in source
    assert "verify_tls" in source


def test_live_validation_script_uses_public_bootstrap_download():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "validate-provider-onboarding.py").read_text()
    assert "/api/v1/provider/bootstrap/{token}" in source
    assert "response.content.startswith" in source
    assert "validation_cleanup" in source

def test_operator_can_generate_gaming_host_profile():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    assert settings["purpose"] == "gaming_host"
    assert settings["ownership_type"] == "khan_cloud"
    assert settings["visibility"] == "internal_only"

    assert settings["allowed_services"]["gaming"] is True
    assert settings["allowed_services"]["streaming"] is True
    assert settings["allowed_services"]["vps"] is False
    assert settings["allowed_services"]["enterprise_vm"] is False
    assert settings["allowed_services"]["gpu_compute"] is False

    assert settings["resource_policy"]["role"] == "gaming_host"
    assert settings["resource_policy"]["gpu_required"] is True
    assert settings["resource_policy"]["execution_backend"] == "windows_native"
    assert settings["resource_policy"]["streaming_backend"] == "sunshine"
    assert settings["resource_policy"]["backend_policy"] == "profile_defined"
    assert settings["resource_policy"]["auto_approve_node"] is True


def test_customer_cannot_generate_khan_cloud_gaming_host_profile():
    with pytest.raises(
        ProviderOnboardingError,
        match="gaming-host onboarding is restricted",
    ):
        _profile_settings_for_role(user("customer"), "gaming_host")


def test_provider_installer_propagates_node_role():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "services" / "provider_onboarding_service.py").read_text()

    assert "node_role: str" in source
    assert '"node_role": node_role' in source
    assert "node_role=payload.node_role" in source


def test_gaming_host_can_target_windows_native():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    assert settings["purpose"] == "gaming_host"
    assert settings["resource_policy"]["execution_backend"] == "windows_native"
    assert settings["resource_policy"]["streaming_backend"] == "sunshine"


def test_gaming_host_linux_is_rejected():
    import pytest
    from app.services.provider_onboarding_service import ProviderOnboardingError

    with pytest.raises(
        ProviderOnboardingError,
        match="Windows",
    ):
        _profile_settings_for_role(
            user("operator"),
            "gaming_host",
            target_platform="linux",
        )

def test_windows_installer_target_is_supported_by_schema():
    from app.schemas.provider_onboarding import NodeInstallerCreate

    payload = NodeInstallerCreate(
        node_role="gaming_host",
        target_platform="windows",
    )

    assert payload.target_platform == "windows"


def test_linux_installer_target_remains_default():
    from app.schemas.provider_onboarding import NodeInstallerCreate

    payload = NodeInstallerCreate(
        node_role="gaming_host",
    )

    assert payload.target_platform == "linux"


def test_provider_service_contains_windows_installer_builder():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (
        root / "app" / "services" / "provider_onboarding_service.py"
    ).read_text()

    assert "_build_windows_installer" in source
    assert "install-runtime.ps1" in source
    assert "windows_native" in source


def test_windows_installer_builder_creates_complete_bundle(monkeypatch, tmp_path):
    import zipfile
    import yaml

    from app.services import provider_onboarding_service as service

    fake_agent = tmp_path / "node-agent"
    deploy = fake_agent / "deploy"
    deploy.mkdir(parents=True)

    (deploy / "install-runtime.ps1").write_text(
        'Write-Host "Khan Cloud Windows installer"\n'
    )
    (fake_agent / "requirements.txt").write_text("pyyaml\n")
    (fake_agent / "agent-marker.txt").write_text("agent payload\n")

    monkeypatch.setattr(service, "AGENT_SOURCE", fake_agent)

    output = tmp_path / "khan-cloud-windows.zip"

    service._build_windows_installer(
        enrollment_code="kc-test-enrollment",
        node_name="KC-WINDOWS-TEST",
        node_role="gaming_host",
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        control_plane_url="http://10.10.20.100:8000",
        verify_tls=False,
        output=output,
    )

    assert output.is_file()

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())

        assert "install.ps1" in names
        assert "config.yaml" in names
        assert "agent/deploy/install-runtime.ps1" in names
        assert "agent/agent-marker.txt" in names

        config = yaml.safe_load(
            archive.read("config.yaml").decode("utf-8")
        )

        assert config["agent"]["node_name"] == "KC-WINDOWS-TEST"
        assert config["agent"]["node_role"] == "gaming_host"
        assert (
            config["agent"]["control_plane_url"]
            == "http://10.10.20.100:8000"
        )

        assert (
            config["security"]["deployment_enrollment_code"]
            == "kc-test-enrollment"
        )
        assert config["security"]["verify_tls"] is False

        assert config["gaming"]["enabled"] is True
        assert (
            config["gaming"]["execution_backend"]
            == "windows_native"
        )
        assert (
            config["gaming"]["streaming_backend"]
            == "sunshine"
        )

        install_script = archive.read("install.ps1").decode("utf-8")

        assert "install-runtime.ps1" in install_script
        assert "-SourceDir" in install_script
        assert "-ConfigFile" in install_script


def test_provider_api_builds_windows_one_command():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "api" / "v1" / "provider.py").read_text()

    assert 'payload.target_platform == "windows"' in source
    assert "Expand-Archive" in source
    assert "install.ps1" in source
    assert "powershell" in source.lower()


def test_provider_api_keeps_linux_one_command():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "api" / "v1" / "provider.py").read_text()

    assert "/tmp/khan-cloud-node.run" in source
    assert "chmod +x" in source


def test_gaming_host_policy_is_windows_only():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    policy = settings["resource_policy"]

    assert policy["role"] == "gaming_host"
    assert policy["supported_platforms"] == ["windows"]


def test_gaming_host_policy_uses_curated_gpu_allowlist():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    gpu = settings["resource_policy"]["gpu_policy"]

    assert gpu["required"] is True
    assert gpu["qualification_mode"] == "allowlist"
    assert "NVIDIA GeForce RTX 3080" in gpu["approved_models"]


def test_gaming_host_policy_defines_driver_qualification():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    driver = settings["resource_policy"]["driver_policy"]

    assert driver["vendor"] == "nvidia"
    assert driver["required"] is True
    assert "approved_branches" in driver


def test_gaming_host_policy_allows_interruptible_auxiliary_workloads():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    workloads = settings["resource_policy"]["workload_policy"]

    assert workloads["primary"] == ["gaming"]
    assert "ai" in workloads["optional_interruptible"]
    assert "rendering" in workloads["optional_interruptible"]
    assert "editing" in workloads["optional_interruptible"]


def test_gaming_host_rejects_unsupported_platform_policy():
    import pytest
    from app.services.provider_onboarding_service import ProviderOnboardingError

    with pytest.raises(
        ProviderOnboardingError,
        match="Windows",
    ):
        _profile_settings_for_role(
            user("operator"),
            "gaming_host",
            target_platform="linux",
        )
