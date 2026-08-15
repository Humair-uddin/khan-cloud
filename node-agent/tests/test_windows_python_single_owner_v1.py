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
