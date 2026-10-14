from pathlib import Path

import pytest


pytestmark = pytest.mark.deployment_safe


ROOT = Path(__file__).resolve().parents[1]


def _runtime_requirements() -> list[str]:
    path = ROOT / "requirements.txt"

    return [
        line.strip().lower()
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
    ]


def test_q38fc_psutil_is_declared_runtime_dependency():
    requirements = _runtime_requirements()

    assert any(
        value.startswith("psutil")
        for value in requirements
    )


def test_q38fc_verified_process_runtime_requires_psutil():
    source = (
        ROOT
        / "khan_agent"
        / "windows_verified_process.py"
    ).read_text(encoding="utf-8")

    assert "import psutil" in source
    assert "psutil.process_iter" in source


def test_q38fc_presentation_runtime_requires_psutil():
    source = (
        ROOT
        / "khan_agent"
        / "windows_presentation.py"
    ).read_text(encoding="utf-8")

    assert "import psutil" in source
    assert "psutil.process_iter" in source


def test_q38hz_installer_has_explicit_runtime_dependency_acceptance_gate():
    source = (
        ROOT
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8-sig")

    dependencies = source.index(
        'Write-Host "===== INSTALL DEPENDENCIES ====="'
    )
    acceptance = source.index(
        'Write-Host "===== VERIFY RUNTIME DEPENDENCIES ====="'
    )
    compile_gate = source.index(
        'Write-Host "===== COMPILE ====="'
    )

    assert dependencies < acceptance < compile_gate
    assert '"psutil"' in source

    for module_name in (
        '"servicemanager"',
        '"win32event"',
        '"win32service"',
        '"win32serviceutil"',
        '"win32ts"',
    ):
        assert module_name in source

    assert 'if sys.platform == "win32":' in source
    assert "importlib.import_module(module_name)" in source
    assert "RUNTIME_DEPENDENCY_IMPORTS=PASS" in source
    assert (
        "Refusing to continue with an incomplete runtime."
        in source
    )


def test_q38hz_dependency_acceptance_precedes_service_configuration():
    source = (
        ROOT
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8-sig")

    acceptance = source.index(
        'Write-Host "===== VERIFY RUNTIME DEPENDENCIES ====="'
    )
    service = source.index(
        'Write-Host "===== INSTALL WINDOWS SERVICE ====="'
    )
    heartbeat = source.index(
        'Write-Host "===== VERIFY HEARTBEAT ====="'
    )
    commit = source.index(
        'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    )

    assert acceptance < service < heartbeat < commit


def test_q38hz_dependency_failure_is_inside_runtime_rollback_boundary():
    source = (
        ROOT
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8-sig")

    transaction_start = source.index(
        'Write-Host "===== CREATE AGENT DIRECTORIES ====="'
    )
    acceptance = source.index(
        'Write-Host "===== VERIFY RUNTIME DEPENDENCIES ====="'
    )
    failure_handler = source.index(
        "$InstallFailure = $_",
        acceptance,
    )

    section = source[acceptance:failure_handler + 500]

    assert transaction_start < acceptance < failure_handler
    assert "if ($RuntimeTransactionActive)" in section
    assert "Restore-KhanCloudRuntime" in section
    assert "throw $InstallFailure" in section


def test_q38hz_rollback_removes_partial_runtime_before_restoring_backup():
    source = (
        ROOT
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8-sig")

    start = source.index(
        "function Restore-KhanCloudRuntime"
    )
    end = source.index(
        'Write-Host "===== QUIESCE EXISTING WINDOWS SERVICE ====="',
        start,
    )
    rollback = source[start:end]

    remove_current = rollback.index(
        "if (Test-Path $Runtime -PathType Container)"
    )
    restore_backup = rollback.index(
        "if ($script:RuntimeBackupCreated)"
    )

    assert remove_current < restore_backup
    assert "Remove-Item" in rollback[remove_current:restore_backup]
    assert "Move-Item" in rollback[restore_backup:]


def test_q38if_dependency_probe_uses_file_not_python_dash_c():
    source = (
        ROOT
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8-sig")

    start = source.index('Write-Host "===== VERIFY RUNTIME DEPENDENCIES ====="')
    end = source.index(
        "# ------------------------------------------------------------\n"
        "# VALIDATION",
        start,
    )
    block = source[start:end]

    assert "$DependencyProbePath = Join-Path" in block
    assert '"runtime-dependency-probe." + $RuntimeTransactionId + ".py"' in block
    assert "Set-Content" in block
    assert "-LiteralPath $DependencyProbePath" in block
    assert "-Arguments @($DependencyProbePath)" in block
    assert (
        '-Description "Khan Cloud runtime dependency verification"'
        in block
    )
    assert "finally {" in block
    assert "Remove-Item" in block

    # Windows PowerShell 5.1 must never transport this multiline program
    # through python.exe -c; native argument marshalling can corrupt it.
    assert "& $Python -c $DependencyProbe" not in block
    assert "-c $DependencyProbe" not in block


def test_q38if_dependency_probe_remains_inside_transaction():
    source = (
        ROOT
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8-sig")

    transaction_start = source.index("$RuntimeTransactionActive = $true")
    acceptance = source.index(
        'Write-Host "===== VERIFY RUNTIME DEPENDENCIES ====="'
    )
    commit = source.index(
        'Write-Host "===== COMMIT RUNTIME TRANSACTION ====="'
    )

    assert transaction_start < acceptance < commit
