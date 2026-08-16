from pathlib import Path


ROOT = Path(__file__).parents[1]
BOOTSTRAP = ROOT / "deploy" / "universal-bootstrap.ps1"
INSTALLER = ROOT / "deploy" / "install-runtime.ps1"
UPDATER = ROOT / "deploy" / "apply-runtime-update.ps1"


def bootstrap_text() -> str:
    return BOOTSTRAP.read_text()


def installer_text() -> str:
    return INSTALLER.read_text()


def updater_text() -> str:
    return UPDATER.read_text()


def test_windows_universal_bootstrap_exists():
    assert BOOTSTRAP.is_file()


def test_bootstrap_requires_administrator():
    text = bootstrap_text()

    assert "Test-Administrator" in text
    assert "must run as Administrator" in text


def test_bootstrap_has_persistent_checkpoints():
    text = bootstrap_text()

    assert r"KhanCloud\Bootstrap" in text
    assert "bootstrap.checkpoints" in text
    assert "Test-Checkpoint" in text
    assert "Set-Checkpoint" in text
    assert 'Set-Checkpoint "completed"' in text


def test_bootstrap_requires_python_312_or_newer():
    text = bootstrap_text()

    assert '$MinimumPythonVersion = "3.12"' in text
    assert "Get-CompatiblePython" in text
    assert "Convert-Version" in text


def test_bootstrap_can_remediate_missing_python():
    text = bootstrap_text()

    assert "Install-PythonSafely" in text
    assert "winget" in text
    assert "Python.Python.3.12" in text
    assert "--scope machine" in text
    assert "--silent" in text
    assert "--accept-package-agreements" in text
    assert "--accept-source-agreements" in text


def test_bootstrap_does_not_download_arbitrary_python_binary():
    text = bootstrap_text()

    forbidden = (
        "Invoke-WebRequest",
        "curl.exe",
        "Start-BitsTransfer",
    )

    for token in forbidden:
        assert token not in text


def test_bootstrap_verifies_venv_capability_before_install():
    text = bootstrap_text()

    assert "-m venv $Probe" in text
    assert "venv_capability_verified" in text


def test_bootstrap_accepts_universal_installer_manifest():
    text = bootstrap_text()

    assert "[string]$InstallerManifest" in text
    assert "installer_manifest_present" in text


def test_bootstrap_reuses_existing_runtime_installer():
    text = bootstrap_text()

    assert r"deploy\install-runtime.ps1" in text
    assert "& $InstallRuntime" in text


def test_runtime_remains_in_isolated_venv():
    bootstrap = bootstrap_text()
    installer = installer_text()

    assert (
        r"KhanCloud\Agent\runtime\.venv\Scripts\python.exe"
        in bootstrap
    )

    assert '$Venv = Join-Path $Runtime ".venv"' in installer
    assert '$Python = Join-Path $Venv "Scripts\\python.exe"' in installer


def test_bootstrap_does_not_install_games_into_python_environment():
    text = bootstrap_text().lower()

    forbidden = (
        "steam install",
        "epic games install",
        "gamepass install",
    )

    for token in forbidden:
        assert token not in text


def test_existing_installer_preserves_credentials_and_identity():
    text = installer_text()

    assert "credentials.json" in text
    assert "identity.json" in text
    assert "Existing credentials found - skipping enrollment." in text


def test_existing_installer_scrubs_enrollment_secret():
    text = installer_text()

    assert 'security["deployment_enrollment_code"] = ""' in text


def test_existing_installer_verifies_service_running():
    text = installer_text()

    assert 'Get-Service -Name $ServiceName' in text
    assert 'if ($Service.Status -ne "Running")' in text


def test_existing_installer_verifies_heartbeat():
    text = installer_text()

    assert "--heartbeat-once" in text


def test_runtime_updater_requires_existing_isolated_runtime():
    text = updater_text()

    assert r'.venv\Scripts\python.exe' in text
    assert "Existing agent Python environment is unavailable" in text


def test_bootstrap_and_updater_have_distinct_responsibilities():
    bootstrap = bootstrap_text()
    updater = updater_text()

    assert "Install-PythonSafely" in bootstrap
    assert "Install-PythonSafely" not in updater


def test_existing_installer_scrubber_uses_python_stdin():
    text = installer_text()

    assert "$ScrubScript = @'" in text
    assert "$ScrubScript | & $Python - $InstalledConfig" in text
    assert "& $Python -c @'" not in text


def test_existing_credentials_still_scrub_fresh_enrollment_code():
    text = installer_text()

    skip = text.index(
        'Write-Host "Existing credentials found - skipping enrollment."'
    )
    scrub = text.index("$ScrubScript | & $Python - $InstalledConfig")

    assert scrub > skip


def test_windows_service_uses_direct_venv_python_host():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    installer = (
        root / "deploy" / "install-runtime.ps1"
    ).read_text()

    service = (
        root / "khan_agent" / "windows_service.py"
    ).read_text()

    assert 'Join-Path $Venv "Scripts\\python.exe"' in installer
    assert "-m khan_agent.windows_service --service" in installer

    assert "pythonservice.exe" not in installer

    assert "servicemanager.Initialize()" in service
    assert (
        "servicemanager.PrepareToHostSingle("
        "KhanCloudAgentService)"
    ) in service
    assert "servicemanager.StartServiceCtrlDispatcher()" in service

    assert 'sys.argv[1:] == ["--service"]' in service


def test_windows_service_management_fallback_remains_available():
    from pathlib import Path

    service = (
        Path(__file__).resolve().parents[1]
        / "khan_agent"
        / "windows_service.py"
    ).read_text()

    assert (
        "win32serviceutil.HandleCommandLine("
        "KhanCloudAgentService)"
    ) in service
