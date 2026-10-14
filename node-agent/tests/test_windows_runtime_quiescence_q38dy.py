from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy" / "install-runtime.ps1"


def test_q38dy_quiescence_precedes_runtime_backup():
    source = INSTALLER.read_text(encoding="utf-8")

    quiesce = source.index(
        "$runtimeQuiesceDeadline = (Get-Date).AddSeconds(30)"
    )
    backup = source.index(
        'Write-Host "===== BACKUP EXISTING RUNTIME ====="'
    )

    assert quiesce < backup


def test_q38dy_checks_executable_and_command_line():
    source = INSTALLER.read_text(encoding="utf-8")

    assert "$_.ExecutablePath.StartsWith(" in source
    assert "$_.CommandLine.IndexOf(" in source
    assert "$Runtime" in source


def test_q38dy_is_bounded_and_fail_closed():
    source = INSTALLER.read_text(encoding="utf-8")

    assert ".AddSeconds(30)" in source
    assert "Start-Sleep -Milliseconds 250" in source
    assert "Refusing runtime mutation." in source
    assert "Remaining processes:" in source


def test_q38dy_does_not_force_kill_runtime_processes():
    source = INSTALLER.read_text(encoding="utf-8")
    block = source[
        source.index("$runtimeQuiesceDeadline"):
        source.index(
            'Write-Host "===== BACKUP EXISTING RUNTIME ====="'
        )
    ]

    assert "Stop-Process" not in block
    assert "taskkill" not in block.lower()



def test_runtime_transaction_establishes_external_working_directory_before_backup():
    source = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8")

    quiesce = source.index(
        'Write-Host "Runtime process quiescence verified."'
    )
    safe_location = source.index(
        "Set-Location -LiteralPath $RuntimeMutationWorkingDirectory"
    )

    backup_candidates = [
        source.find("BACKUP EXISTING RUNTIME", safe_location),
        source.find("runtime.rollback", safe_location),
    ]
    backup_candidates = [
        value for value in backup_candidates
        if value >= 0
    ]

    assert backup_candidates
    backup = min(backup_candidates)

    assert quiesce < safe_location < backup
    assert "$RuntimeMutationWorkingDirectory = $AgentRoot" in source


def test_runtime_transaction_proves_root_rename_readiness_before_backup():
    source = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8")

    readiness = source.index(
        'Write-Host "Runtime root rename-readiness verified."'
    )

    backup_candidates = [
        source.find("BACKUP EXISTING RUNTIME", readiness),
        source.find("runtime.rollback", readiness),
    ]
    backup_candidates = [
        value for value in backup_candidates
        if value >= 0
    ]

    assert backup_candidates
    backup = min(backup_candidates)

    assert readiness < backup
    assert "$RuntimeReadinessCanary" in source
    assert "$RuntimeReadinessDeadline" in source
    assert "[System.IO.Directory]::Move(" in source
    assert "Start-Sleep -Milliseconds 250" in source
    assert (
        "Khan Cloud runtime root did not become "
        in source
    )
