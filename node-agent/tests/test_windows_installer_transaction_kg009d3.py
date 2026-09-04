from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-runtime.ps1"


def source() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_service_quiesces_before_runtime_mutation():
    text = source()

    quiesce = text.index(
        'Write-Host "===== QUIESCE EXISTING WINDOWS SERVICE ====="'
    )
    backup = text.index(
        'Write-Host "===== BACKUP EXISTING RUNTIME ====="'
    )
    deploy = text.index(
        'Write-Host "===== DEPLOY RUNTIME ====="'
    )
    dependencies = text.index(
        'Write-Host "===== INSTALL DEPENDENCIES ====="'
    )

    assert quiesce < backup < deploy < dependencies
    assert "Stop-Service" in text
    assert "WaitForStatus" in text
    assert "did not quiesce before runtime mutation" in text


def test_runtime_backup_contains_old_runtime_before_new_runtime_creation():
    text = source()

    assert '$RuntimeBackup = Join-Path $AgentRoot "runtime.rollback"' in text
    assert "$RuntimeBackupCreated = $false" in text

    backup = text.index(
        'Write-Host "===== BACKUP EXISTING RUNTIME ====="'
    )
    create = text.index(
        'Write-Host "===== CREATE AGENT DIRECTORIES ====="'
    )

    assert backup < create
    assert "Move-Item" in text
    assert "$RuntimeBackupCreated = $true" in text


def test_new_runtime_gets_fresh_virtual_environment():
    text = source()

    backup = text.index(
        'Write-Host "===== BACKUP EXISTING RUNTIME ====="'
    )
    venv = text.index(
        'Write-Host "===== CREATE PYTHON ENVIRONMENT ====="'
    )

    assert backup < venv
    assert "& $SystemPython -m venv $Venv" in text




def test_upgrade_preserves_existing_scm_service_registration():
    text = source()

    assert "sc.exe config" in text

    service_section = text.index(
        'Write-Host "===== INSTALL WINDOWS SERVICE ====="'
    )
    heartbeat = text.index(
        'Write-Host "===== VERIFY HEARTBEAT ====="'
    )

    section = text[service_section:heartbeat]

    assert "sc.exe delete" not in section
    assert "if (-not $ExistingService)" in section
    assert "sc.exe create" in section
    assert "sc.exe config" in section


def test_rollback_restores_runtime_and_previously_running_service():
    text = source()

    assert "function Restore-KhanCloudRuntime" in text
    assert 'Write-Host "===== ROLLBACK WINDOWS RUNTIME ====="' in text
    assert "if ($script:RuntimeBackupCreated)" in text
    assert "$RuntimeBackup" in text
    assert "$Runtime" in text

    assert "$script:ExistingServiceWasRunning" in text
    assert "Start-Service" in text
    assert (
        "[System.ServiceProcess.ServiceControllerStatus]::Running"
        in text
    )


def test_failed_first_install_removes_service_created_by_failed_transaction():
    text = source()

    rollback = text.index("function Restore-KhanCloudRuntime")
    quiesce = text.index(
        'Write-Host "===== QUIESCE EXISTING WINDOWS SERVICE ====="'
    )

    section = text[rollback:quiesce]

    assert "-not $script:ExistingServicePresent" in section
    assert "sc.exe delete" in section


def test_success_commits_only_after_heartbeat_validation():
    text = source()

    heartbeat = text.index(
        'Write-Host "===== VERIFY HEARTBEAT ====="'
    )
    commit = text.index(
        'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    )

    assert heartbeat < commit
    assert "$RuntimeTransactionActive = $false" in text

    commit_section = text[commit:]
    assert "Remove-Item" in commit_section
    assert "$RuntimeBackup" in commit_section


def test_transaction_failure_enters_rollback_and_rethrows_original_failure():
    text = source()

    assert "$InstallFailure = $_" in text
    assert "if ($RuntimeTransactionActive)" in text
    assert "Restore-KhanCloudRuntime" in text
    assert "throw $InstallFailure" in text


def test_identity_and_credentials_remain_outside_runtime_transaction():
    text = source()

    assert '$Credentials = Join-Path $AgentRoot "credentials.json"' in text
    assert '$Identity = Join-Path $AgentRoot "identity.json"' in text
    assert '$Runtime = Join-Path $AgentRoot "runtime"' in text
    assert '$RuntimeBackup = Join-Path $AgentRoot "runtime.rollback"' in text


def test_transaction_preparation_failure_restores_previous_running_service():
    text = source()

    quiesce = text.index(
        'Write-Host "===== QUIESCE EXISTING WINDOWS SERVICE ====="'
    )
    runtime_try = text.index(
        'Write-Host "===== CREATE AGENT DIRECTORIES ====="'
    )

    preparation = text[quiesce:runtime_try]

    assert "$PreparationFailure = $_" in preparation
    assert "$ExistingServiceWasRunning" in preparation
    assert "$ServiceAfterPreparationFailure" in preparation
    assert "Start-Service" in preparation
    assert (
        "[System.ServiceProcess.ServiceControllerStatus]::Running"
        in preparation
    )
    assert "throw $PreparationFailure" in preparation


def test_transaction_activation_occurs_only_after_runtime_backup_succeeds():
    text = source()

    backup = text.index(
        'Write-Host "===== BACKUP EXISTING RUNTIME ====="'
    )
    active = text.index(
        "$RuntimeTransactionActive = $true",
        backup,
    )
    runtime_try = text.index(
        'Write-Host "===== CREATE AGENT DIRECTORIES ====="'
    )

    assert backup < active < runtime_try
    assert "-ErrorAction Stop" in text[backup:active]




def test_bounded_python_uses_dotnet_process_not_start_process():
    source = Path("deploy/install-runtime.ps1").read_text(
        encoding="utf-8-sig"
    )

    start = source.index(
        "function Invoke-BoundedPythonCommand"
    )
    end = source.index(
        "function Restore-KhanCloudRuntime",
        start,
    )
    bounded = source[start:end]

    assert "System.Diagnostics.ProcessStartInfo" in bounded
    assert "System.Diagnostics.Process" in bounded
    assert "$Process.Start()" in bounded
    assert "$Process.WaitForExit(" in bounded
    assert "$Process.ExitCode" in bounded
    assert "Start-Process" not in bounded


def test_bounded_python_quotes_windows_process_arguments():
    source = Path("deploy/install-runtime.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert "$QuotedArguments" in source
    assert "$StartInfo.Arguments = $QuotedArguments -join" in source
    assert "$Value -match '[\\s\"]'" in source


def test_bounded_python_preserves_timeout_tree_kill():
    source = Path("deploy/install-runtime.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert "& taskkill.exe" in source
    assert "/PID $Process.Id" in source
    assert "/T" in source
    assert "/F" in source
    assert 'throw "$Description timed out."' in source


def test_bounded_python_reads_exit_code_after_completed_wait():
    source = Path("deploy/install-runtime.ps1").read_text(
        encoding="utf-8-sig"
    )

    start = source.index(
        "function Invoke-BoundedPythonCommand"
    )
    end = source.index(
        "function Restore-KhanCloudRuntime",
        start,
    )
    bounded = source[start:end]

    completed = bounded.index(
        "$Completed = $Process.WaitForExit("
    )
    final_wait = bounded.index(
        "$Process.WaitForExit()",
        completed,
    )
    exit_code = bounded.index(
        "$ProcessExitCode = [int]$Process.ExitCode",
        final_wait,
    )

    assert completed < final_wait < exit_code

def test_pip_execution_is_bounded_noninteractive_and_tree_killed():
    text = source()

    assert "function Invoke-BoundedPythonCommand" in text
    assert "$DependencyTimeoutSeconds = 600" in text

    start = text.index(
        "function Invoke-BoundedPythonCommand"
    )
    end = text.index(
        "function Restore-KhanCloudRuntime",
        start,
    )
    bounded = text[start:end]

    assert "System.Diagnostics.ProcessStartInfo" in bounded
    assert "System.Diagnostics.Process" in bounded
    assert "$Completed = $Process.WaitForExit(" in bounded
    assert "& taskkill.exe" in bounded
    assert "/PID $Process.Id" in bounded
    assert "/T" in bounded
    assert "/F" in bounded

    assert '"--disable-pip-version-check"' in text
    assert '"--no-input"' in text


def test_bounded_python_wait_finalizes_before_exit_code_snapshot():
    text = source()

    start = text.index(
        "function Invoke-BoundedPythonCommand"
    )
    end = text.index(
        "function Restore-KhanCloudRuntime",
        start,
    )
    bounded = text[start:end]

    timed_wait = bounded.index(
        "$Completed = $Process.WaitForExit("
    )
    final_wait = bounded.index(
        "$Process.WaitForExit()",
        timed_wait,
    )
    exit_code = bounded.index(
        "$ProcessExitCode = [int]$Process.ExitCode",
        final_wait,
    )

    assert timed_wait < final_wait < exit_code


def test_bounded_python_uses_stable_typed_exit_code_snapshot():
    text = source()

    start = text.index(
        "function Invoke-BoundedPythonCommand"
    )
    end = text.index(
        "function Restore-KhanCloudRuntime",
        start,
    )
    bounded = text[start:end]

    assert (
        "$ProcessExitCode = [int]$Process.ExitCode"
        in bounded
    )
    assert (
        "if ($ProcessExitCode -ne 0)"
        in bounded
    )

    assert "$Child.ExitCode" not in bounded
    assert "$Child.WaitForExit" not in bounded




def test_sunshine_protected_credential_is_configured_before_service_start():
    text = source()

    sunshine = text.index(
        'Write-Host "===== CONFIGURE SUNSHINE PROTECTED CREDENTIAL ====="'
    )

    service = text.index(
        'Write-Host "===== INSTALL WINDOWS SERVICE ====="'
    )

    heartbeat = text.index(
        'Write-Host "===== VERIFY HEARTBEAT ====="'
    )

    commit = text.index(
        'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    )

    assert sunshine < service < heartbeat < commit

    assert (
        "configure-windows-sunshine.ps1"
        in text
    )

    assert (
        'SunshineCredentialSource -eq "windows_lsa"'
        in text
    )

    assert "SunshineHasPlaintextPassword" in text


def test_sunshine_lsa_policy_refuses_plaintext_config_secret():
    text = source()

    assert (
        "SunshineHasPlaintextPassword"
        in text
    )

    assert (
        "must not contain sunshine_api_password"
        in text
    )


def test_sunshine_external_state_has_repair_contract():
    text = (
        Path("deploy/configure-windows-sunshine.ps1")
        .read_text(encoding="utf-8")
    )

    assert 'Status "repair_required"' in text

    assert (
        "[KhanLsaSecret]::Retrieve"
        in text
    )

    assert (
        "[KhanLsaSecret]::Store"
        in text
    )

    assert (
        "SECRET_VALUE_PRINTED=NO"
        in text
    )

    assert (
        "WINDOWS_REBOOT_REQUIRED=NO"
        in text
    )
