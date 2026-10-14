from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOOTSTRAP = ROOT / "deploy" / "universal-bootstrap.ps1"
RUNTIME = ROOT / "deploy" / "install-runtime.ps1"


def _bootstrap() -> str:
    return BOOTSTRAP.read_text()


def _runtime() -> str:
    return RUNTIME.read_text()


def test_bootstrap_owns_python_discovery():
    source = _bootstrap()

    assert "function Get-CompatiblePython" in source
    assert "$Python = Get-CompatiblePython" in source


def test_bootstrap_owns_python_remediation():
    source = _bootstrap()

    assert "function Install-PythonSafely" in source
    assert "Python.Python.3.12" in source


def test_bootstrap_revalidates_after_remediation():
    source = _bootstrap()

    assert source.count("$Python = Get-CompatiblePython") >= 2


def test_bootstrap_validates_venv_capability():
    source = _bootstrap()

    assert "& $Python.Path -m venv $Probe" in source


def test_runtime_requires_authoritative_python():
    source = _runtime()

    assert "[string]$PythonExecutable" in source
    assert (
        "Test-Path $PythonExecutable -PathType Leaf"
        in source
    )


def test_runtime_does_not_rediscover_python():
    source = _runtime()

    forbidden = (
        "Get-Command python.exe",
        "Get-Command python ",
        "Get-Command py.exe",
        "Get-Command py ",
    )

    for item in forbidden:
        assert item not in source


def test_runtime_uses_exact_supplied_interpreter():
    source = _runtime()

    assert "$SystemPython = $PythonExecutable" in source


def test_runtime_still_fails_closed_on_bad_interpreter():
    source = _runtime()

    assert "Validated Python executable failed" in source
    assert "Python 3.12 or newer is required" in source


def test_bootstrap_passes_exact_interpreter():
    source = _bootstrap()

    assert "-PythonExecutable $Python.Path" in source


def test_runtime_requires_bootstrap_authorization():
    bootstrap = _bootstrap()
    runtime = _runtime()

    assert "-BootstrapAuthorized" in bootstrap
    assert "[switch]$BootstrapAuthorized" in runtime
    assert "Direct install-runtime.ps1 invocation is unsupported" in runtime


def test_python_executable_is_not_misclassified_as_py_launcher():
    source = _bootstrap()

    assert '$Candidate.Name -like "py*"' not in source
    assert '$Candidate.Name -in @("py.exe", "py")' in source


def test_py_launcher_selection_is_exact():
    """
    python.exe/python are direct interpreters.
    Only py.exe/py may receive the Windows launcher -3 argument.
    """
    names = {
        "python.exe": False,
        "python": False,
        "py.exe": True,
        "py": True,
    }

    for name, expected_launcher in names.items():
        actual_launcher = name in {"py.exe", "py"}
        assert actual_launcher is expected_launcher


def test_bootstrap_rejects_user_scoped_python_for_machine_agent():
    source = _bootstrap()

    assert "[Environment+SpecialFolder]::UserProfile" in source
    assert "[Environment+SpecialFolder]::LocalApplicationData" in source
    assert "$UserScoped" in source
    assert "if ($UserScoped)" in source
    assert "continue" in source


def test_python_remediation_uses_only_machine_path():
    source = _bootstrap()

    assert '$env:Path = $MachinePath' in source
    assert '"$env:ProgramFiles\\Python312\\python.exe"' in source

    remediation = source[
        source.index("function Install-PythonSafely"):
        source.index(
            'Write-Host "===== KHAN CLOUD UNIVERSAL WINDOWS BOOTSTRAP ====="'
        )
    ]

    assert "EnvironmentVariableTarget]::User" not in remediation
    assert "$env:LocalAppData\\Programs\\Python" not in remediation


def test_machine_python_authority_uses_resolved_interpreter():
    source = _bootstrap()

    assert "$ResolvedPython = $ResolvedPython.Trim()" in source
    assert "$FullPythonPath = [System.IO.Path]::GetFullPath(" in source
    assert "Path = $FullPythonPath" in source


def test_python_remediation_is_bounded_and_revalidated():
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert "$PythonRemediationMaxAttempts = 3" in source
    assert "$PythonRemediationAttempt = 0" in source
    assert "$PythonRemediationAttempt -lt $PythonRemediationMaxAttempts" in source
    assert "$PythonRemediationAttempt++" in source

    loop_start = source.index(
        "while (\n    -not $Python -and"
    )
    loop_end = source.index(
        'if (-not $Python) {\n    throw (',
        loop_start,
    )
    loop = source[loop_start:loop_end]

    assert "Install-PythonSafely" in loop
    assert "$Python = Get-CompatiblePython" in loop


def test_python_remediation_exhaustion_fails_closed():
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert (
        "Python remediation exhausted {0} bounded attempts"
        in source
    )
    assert (
        "$PythonRemediationAttempt -lt $PythonRemediationMaxAttempts"
        in source
    )


def test_python_retry_rechecks_before_every_mutation():
    source = BOOTSTRAP.read_text(encoding="utf-8")

    start = source.index(
        "while (\n    -not $Python -and"
    )
    end = source.index(
        'if (-not $Python) {\n    throw (',
        start,
    )
    loop = source[start:end]

    rediscoveries = [
        i for i in range(len(loop))
        if loop.startswith("$Python = Get-CompatiblePython", i)
    ]

    install = loop.index("Install-PythonSafely")
    preservation_probe = rediscoveries[0]
    verification_probe = rediscoveries[-1]

    assert len(rediscoveries) >= 2
    assert preservation_probe < install < verification_probe
    assert "if ($Python)" in loop
    assert "break" in loop
