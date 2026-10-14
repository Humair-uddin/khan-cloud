from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

POLICY = (
    ROOT
    / "deploy"
    / "configure-windows-sunshine-apps.ps1"
)

INSTALLER = ROOT / "deploy" / "install-runtime.ps1"


def _policy_text() -> str:
    return POLICY.read_text(encoding="utf-8")


def test_sunshine_application_policy_exists():
    assert POLICY.is_file()


def test_policy_defines_khan_cloud_session():
    text = _policy_text()

    assert 'name = "Khan Cloud Session"' in text
    assert '"image-path" = "desktop.png"' in text


def test_policy_has_no_launcher_lifecycle_command():
    text = _policy_text().lower()

    assert "steam://open/bigpicture" not in text
    assert "steam://close/bigpicture" not in text
    assert "steam://run/" not in text
    assert "steam://rungameid/" not in text


def test_policy_forbids_launcher_ownership_fields():
    text = _policy_text()

    for field in (
        '"cmd"',
        '"detached"',
        '"prep-cmd"',
        '"auto-detach"',
        '"wait-all"',
        '"exit-timeout"',
    ):
        assert field in text


def test_policy_is_idempotent():
    text = _policy_text()

    assert "Test-KhanCloudApplicationPolicy" in text
    assert "SUNSHINE_APP_POLICY_ALREADY_CANONICAL=YES" in text
    assert "SUNSHINE_APP_POLICY_CHANGED=NO" in text


def test_policy_uses_transactional_temp_file():
    text = _policy_text()

    assert "$Path.khancloud.tmp" in text
    assert "Move-Item" in text
    assert "-Force" in text


def test_policy_does_not_restart_sunshine():
    text = _policy_text()

    assert "Restart-Service" not in text
    assert "Stop-Service" not in text
    assert "Start-Service" not in text


def test_installer_invokes_application_policy():
    text = INSTALLER.read_text(encoding="utf-8")

    assert "configure-windows-sunshine-apps.ps1" in text
    assert "CONFIGURE SUNSHINE APPLICATION POLICY" in text
    assert "$SunshineGamingEnabled" in text
    assert '$SunshineBackend -eq "sunshine"' in text
