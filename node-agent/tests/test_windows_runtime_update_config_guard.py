from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "apply-runtime-update.ps1"
)


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_runtime_updater_avoids_config_self_copy():
    source = _source()

    assert "$ResolvedConfigFile = (Resolve-Path $ConfigFile).Path" in source
    assert "$ResolvedInstalledConfig" in source
    assert "$ResolvedConfigFile -ieq $ResolvedInstalledConfig" in source

    assert (
        'Installed configuration already supplied - preserving existing config.yaml'
        in source
    )


def test_runtime_updater_still_copies_external_config():
    source = _source()

    assert "else {" in source
    assert "Copy-Item $ConfigFile $InstalledConfig -Force" in source


def test_runtime_updater_preserves_identity_preflight():
    source = _source()

    assert "Existing node credentials are missing" in source
    assert "Existing node identity is missing" in source
    assert "Copy-Item $Credentials" in source
    assert "Copy-Item $Identity" in source
