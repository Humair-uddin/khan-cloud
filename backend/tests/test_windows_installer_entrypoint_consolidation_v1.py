import zipfile


def test_generated_windows_installer_preparses_internal_powershell(tmp_path):
    from app.services import provider_onboarding_service as service

    output = tmp_path / "windows-gaming-host.zip"

    manifest = {
        "feature_pack": {
            "id": "FP-GAMING-WINDOWS",
            "name": "Windows Gaming Host",
            "version": "1.0.0",
        },
        "deployment": {
            "purpose": "gaming_host",
            "platform": "windows",
            "execution_backend": "windows_native",
            "streaming_backend": "sunshine",
        },
        "qualification": {},
        "components": {},
    }

    service._build_windows_installer(
        enrollment_code="kc-test-enrollment",
        node_name="KC-WINDOWS-CONSOLIDATION",
        node_role="gaming_host",
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        control_plane_url="http://10.10.20.100:8000",
        verify_tls=False,
        output=output,
        installer_manifest=manifest,
    )

    with zipfile.ZipFile(output) as archive:
        wrapper = archive.read("install.ps1").decode("utf-8")

    assert "System.Management.Automation.Language.Parser" in wrapper
    assert "ParseFile" in wrapper
    assert "universal-bootstrap.ps1" in wrapper
    assert "install-runtime.ps1" in wrapper
    assert "apply-runtime-update.ps1" in wrapper
    assert "PowerShell parser validation failed" in wrapper
    assert '& $Bootstrap ' in wrapper
    assert '-InstallerManifest "$Here\\installer-manifest.yaml"' in wrapper


def test_generated_windows_installer_never_directly_enters_runtime_engine(tmp_path):
    from app.services import provider_onboarding_service as service

    output = tmp_path / "windows-entrypoint.zip"

    service._build_windows_installer(
        enrollment_code="kc-test-enrollment",
        node_name="KC-WINDOWS-ENTRYPOINT",
        node_role="gaming_host",
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        control_plane_url="http://10.10.20.100:8000",
        verify_tls=False,
        output=output,
        installer_manifest={
            "feature_pack": {
                "id": "FP-GAMING-WINDOWS",
                "name": "Windows Gaming Host",
                "version": "1.0.0",
            },
            "deployment": {
                "purpose": "gaming_host",
                "platform": "windows",
            },
            "components": {},
        },
    )

    with zipfile.ZipFile(output) as archive:
        wrapper = archive.read("install.ps1").decode("utf-8")

    invocation_lines = [
        line.strip()
        for line in wrapper.splitlines()
        if line.strip().startswith("& ")
    ]

    assert invocation_lines == [
        '& $Bootstrap -SourceDir "$Here\\agent" '
        '-ConfigFile "$Here\\config.yaml" '
        '-InstallerManifest "$Here\\installer-manifest.yaml"'
    ]
