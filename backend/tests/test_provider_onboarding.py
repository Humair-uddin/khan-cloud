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

        assert "universal-bootstrap.ps1" in install_script
        assert '-SourceDir "$Here\\agent"' in install_script
        assert '-ConfigFile "$Here\\config.yaml"' in install_script
        assert (
            '-InstallerManifest "$Here\\installer-manifest.yaml"'
            in install_script
        )
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



def test_gaming_host_policy_uses_capability_qualification():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    gpu = settings["resource_policy"]["gpu_policy"]
    driver = settings["resource_policy"]["driver_policy"]

    assert gpu["required"] is True
    assert gpu["qualification_mode"] == "capability"
    assert gpu["vendor"] == "nvidia"

    # Hard gaming-host admission floor.
    assert gpu["minimum_vram_mb"] == 8192
    assert gpu["require_operational_gpu"] is True
    assert (
        "hardware_video_encode"
        in gpu["required_capabilities"]
    )

    # New GPUs do not require additions to a model allowlist.
    assert gpu["approved_models"] == []

    # Quality grading remains separate from admission.
    assert (
        gpu["quality_policy"]["baseline"]["minimum_vram_mb"]
        == 8192
    )
    assert (
        gpu["quality_policy"]["grading"]
        == "capability_and_performance"
    )

    # Khan Cloud validates the provider's existing working
    # driver rather than replacing/upgrading it automatically.
    assert driver["vendor"] == "nvidia"
    assert driver["required"] is True
    assert driver["management"] == "preserve_existing"
    assert driver["require_operational"] is True
    assert driver["automatic_upgrade"] is False
    assert driver["minimum_version"] is None
    assert driver["approved_branches"] == []

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


def test_gaming_policy_builds_universal_installer_manifest():
    from app.services.provider_onboarding_service import (
        _build_installer_manifest,
    )

    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    manifest = _build_installer_manifest(
        node_role="gaming_host",
        target_platform="windows",
        settings=settings,
    )

    assert manifest["feature_pack"]["id"] == "FP-GAMING-WINDOWS"

    assert manifest["deployment"] == {
        "purpose": "gaming_host",
        "platform": "windows",
        "execution_backend": "windows_native",
        "streaming_backend": "sunshine",
    }

    assert manifest["qualification"]["gpu"]["required"] is True
    assert (
        manifest["qualification"]["gpu"]["qualification_mode"]
        == "capability"
    )
    assert (
        manifest["qualification"]["gpu"]["approved_models"]
        == []
    )

    assert manifest["qualification"]["driver"]["vendor"] == "nvidia"
    assert manifest["qualification"]["driver"]["required"] is True

    assert manifest["qualification"]["workloads"]["primary"] == [
        "gaming"
    ]
    assert (
        "ai"
        in manifest["qualification"]["workloads"][
            "optional_interruptible"
        ]
    )


def test_windows_bundle_contains_universal_manifest(
    monkeypatch,
    tmp_path,
):
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

    monkeypatch.setattr(service, "AGENT_SOURCE", fake_agent)

    settings = service._profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    output = tmp_path / "gaming-host.zip"

    service._build_windows_installer(
        enrollment_code="kc-test-enrollment",
        node_name="KC-GAMING-TEST",
        node_role="gaming_host",
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        control_plane_url="http://10.10.20.100:8000",
        verify_tls=False,
        output=output,
        installer_manifest=service._build_installer_manifest(
            node_role="gaming_host",
            target_platform="windows",
            settings=settings,
        ),
    )

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())

        assert "installer-manifest.yaml" in names

        manifest = yaml.safe_load(
            archive.read(
                "installer-manifest.yaml"
            ).decode("utf-8")
        )

    assert manifest["deployment"]["purpose"] == "gaming_host"
    assert manifest["deployment"]["platform"] == "windows"

    assert (
        manifest["qualification"]["gpu"]["approved_models"]
        == []
    )


def test_windows_provider_bundle_uses_universal_bootstrap_source():
    from app.services import provider_onboarding_service as service

    bootstrap = (
        service.AGENT_SOURCE
        / "deploy"
        / "universal-bootstrap.ps1"
    )

    assert bootstrap.is_file()

    text = bootstrap.read_text()

    assert "KHAN CLOUD UNIVERSAL WINDOWS BOOTSTRAP" in text
    assert "Install-PythonSafely" in text
    assert "[string]$InstallerManifest" in text
    assert 'Test-Path $InstallerManifest -PathType Leaf' in text
    assert "installer_manifest_present" in text


def test_windows_universal_bootstrap_is_policy_neutral():
    from app.services import provider_onboarding_service as service

    bootstrap = (
        service.AGENT_SOURCE
        / "deploy"
        / "universal-bootstrap.ps1"
    ).read_text().lower()

    # Machine bootstrap is generic. Gaming policy belongs to the
    # manifest/control-plane/installer qualification layer.
    assert "rtx 3080" not in bootstrap
    assert "rtx 5070" not in bootstrap
    assert "gaming price" not in bootstrap


def test_windows_gaming_bundle_is_self_contained_for_universal_bootstrap(
    monkeypatch,
    tmp_path,
):
    import zipfile
    import yaml

    from app.services import provider_onboarding_service as service

    fake_agent = tmp_path / "node-agent"
    deploy = fake_agent / "deploy"
    deploy.mkdir(parents=True)

    (deploy / "install-runtime.ps1").write_text(
        'Write-Host "runtime installer"\n'
    )

    # The universal bootstrap must be included in the actual bundle.
    source_bootstrap = (
        service.AGENT_SOURCE
        / "deploy"
        / "universal-bootstrap.ps1"
    )

    (deploy / "universal-bootstrap.ps1").write_text(
        source_bootstrap.read_text()
    )

    (fake_agent / "requirements.txt").write_text("pyyaml\n")
    (fake_agent / "agent-marker.txt").write_text("agent payload\n")

    monkeypatch.setattr(service, "AGENT_SOURCE", fake_agent)

    settings = service._profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    manifest = service._build_installer_manifest(
        node_role="gaming_host",
        target_platform="windows",
        settings=settings,
    )

    output = tmp_path / "gaming-universal.zip"

    service._build_windows_installer(
        enrollment_code="kc-test-enrollment",
        node_name="KC-GAMING-UNIVERSAL",
        node_role="gaming_host",
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        control_plane_url="http://10.10.20.100:8000",
        verify_tls=False,
        output=output,
        installer_manifest=manifest,
    )

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())

        assert "install.ps1" in names
        assert "config.yaml" in names
        assert "installer-manifest.yaml" in names

        assert (
            "agent/deploy/universal-bootstrap.ps1"
            in names
        )

        assert (
            "agent/deploy/install-runtime.ps1"
            in names
        )

        wrapper = archive.read(
            "install.ps1"
        ).decode("utf-8")

        assert "universal-bootstrap.ps1" in wrapper

        assert (
            '-InstallerManifest '
            '"$Here\\installer-manifest.yaml"'
            in wrapper
        )

        packaged_manifest = yaml.safe_load(
            archive.read(
                "installer-manifest.yaml"
            ).decode("utf-8")
        )

        assert (
            packaged_manifest["deployment"]["purpose"]
            == "gaming_host"
        )

        assert (
            packaged_manifest["deployment"]["platform"]
            == "windows"
        )

        assert (
            packaged_manifest["deployment"]["execution_backend"]
            == "windows_native"
        )

        assert (
            packaged_manifest["deployment"]["streaming_backend"]
            == "sunshine"
        )

        assert (
            packaged_manifest["qualification"]["gpu"]["required"]
            is True
        )

        assert (
            packaged_manifest["qualification"]["gpu"][
                "qualification_mode"
            ]
            == "capability"
        )


def test_gaming_host_uses_capability_based_gpu_policy():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    gpu = settings["resource_policy"]["gpu_policy"]

    assert gpu["required"] is True
    assert gpu["qualification_mode"] == "capability"
    assert gpu["minimum_vram_mb"] == 8192
    assert gpu["require_operational_gpu"] is True

    assert (
        "hardware_video_encode"
        in gpu["required_capabilities"]
    )


def test_gaming_host_preserves_working_customer_driver():
    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    driver = settings["resource_policy"]["driver_policy"]

    assert driver["vendor"] == "nvidia"
    assert driver["management"] == "preserve_existing"
    assert driver["require_operational"] is True
    assert driver["automatic_upgrade"] is False


def test_gaming_manifest_carries_8gb_capability_policy():
    from app.services.provider_onboarding_service import (
        _build_installer_manifest,
    )

    settings = _profile_settings_for_role(
        user("operator"),
        "gaming_host",
        target_platform="windows",
    )

    manifest = _build_installer_manifest(
        node_role="gaming_host",
        target_platform="windows",
        settings=settings,
    )

    gpu = manifest["qualification"]["gpu"]
    driver = manifest["qualification"]["driver"]

    assert gpu["qualification_mode"] == "capability"
    assert gpu["minimum_vram_mb"] == 8192
    assert gpu["require_operational_gpu"] is True

    assert driver["management"] == "preserve_existing"
    assert driver["automatic_upgrade"] is False
