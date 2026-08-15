import platform
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "deploy" / "universal-bootstrap.ps1"
RUNTIME = ROOT / "deploy" / "install-runtime.ps1"


def _bootstrap() -> str:
    return BOOTSTRAP.read_text()


def _runtime() -> str:
    return RUNTIME.read_text()


def test_bootstrap_uses_valid_single_line_environment_type_literals():
    source = _bootstrap()

    assert "[Environment]::GetEnvironmentVariable(" in source
    assert "$MachinePath = [\n" not in source
    assert "$UserPath = [\n" not in source


def test_bootstrap_is_only_public_first_install_entrypoint():
    source = _bootstrap()
    runtime = _runtime()

    assert "-BootstrapAuthorized" in source
    assert "[switch]$BootstrapAuthorized" in runtime
    assert "Direct install-runtime.ps1 invocation is unsupported" in runtime
    assert "universal-bootstrap.ps1" in runtime


def test_runtime_does_not_own_prerequisite_discovery_or_remediation():
    source = _runtime().lower()

    forbidden = (
        "get-compatiblepython",
        "install-pythonsafely",
        "python.python.3.12",
        "get-command winget",
        "winget install",
        "get-command python.exe",
        "get-command py.exe",
    )

    for item in forbidden:
        assert item not in source


def test_runtime_requires_bootstrap_supplied_interpreter_but_does_not_prompt():
    source = _runtime()

    assert '[string]$PythonExecutable = ""' in source
    assert "[Parameter(Mandatory = $true)]\n    [string]$PythonExecutable" not in source
    assert "Test-Path $PythonExecutable -PathType Leaf" in source
    assert "$SystemPython = $PythonExecutable" in source


def test_bootstrap_preserves_provider_owned_gpu_and_streaming_software():
    source = _bootstrap().lower()

    forbidden = (
        "nvidia driver install",
        "uninstall nvidia",
        "winget uninstall sunshine",
        "remove-item sunshine",
        "stop-process sunshine",
        "taskkill",
    )

    for item in forbidden:
        assert item not in source


def _powershell_executable() -> str | None:
    for name in ("pwsh", "powershell", "powershell.exe"):
        value = shutil.which(name)
        if value:
            return value
    return None


@pytest.mark.skipif(
    _powershell_executable() is None,
    reason="PowerShell parser is unavailable on this test host",
)
def test_windows_scripts_parse_with_real_powershell_parser():
    exe = _powershell_executable()
    assert exe is not None

    for script in (BOOTSTRAP, RUNTIME):
        command = (
            "$errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}',"
            "[ref]$null,[ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { "
            "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
        )
        completed = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, (
            f"PowerShell parser rejected {script}:\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def test_installer_responsibility_split_is_documented_in_scripts():
    bootstrap = _bootstrap()
    runtime = _runtime()

    assert "safely discover/remediate Python" in bootstrap
    assert "invoke the existing production runtime installer" in bootstrap
    assert "internal execution engine" in runtime
    assert "must enter through universal-bootstrap.ps1" in runtime
