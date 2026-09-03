import pytest
from pathlib import Path

from khan_agent import gaming_inventory
from khan_agent.windows_session_broker import InteractiveSession


ROOT = Path(__file__).resolve().parents[1]


def test_inventory_uses_authoritative_session_broker(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_inventory.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        gaming_inventory,
        "discover_interactive_session",
        lambda: InteractiveSession(
            session_id=6,
            available=True,
            source="managed_console",
            managed=True,
            username="KC-HOST\\KhanGaming",
            broker_mode="managed_autologon",
        ),
    )

    value = gaming_inventory.collect_interactive_session()

    assert value == {
        "available": True,
        "session_id": 6,
        "username": "KC-HOST\\KhanGaming",
        "managed": True,
        "source": "managed_console",
        "broker_mode": "managed_autologon",
    }


def test_inventory_reports_existing_console(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_inventory.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        gaming_inventory,
        "discover_interactive_session",
        lambda: InteractiveSession(
            session_id=2,
            available=True,
            source="active_console",
            managed=False,
            username="KC-HOST\\Operator",
            broker_mode="existing",
        ),
    )

    value = gaming_inventory.collect_interactive_session()

    assert value["available"] is True
    assert value["session_id"] == 2
    assert value["managed"] is False
    assert value["broker_mode"] == "existing"


def test_runtime_installer_owns_managed_broker_configuration():
    text = (
        ROOT / "deploy" / "install-runtime.ps1"
    ).read_text(encoding="utf-8")

    assert (
        "CONFIGURE WINDOWS GAMING SESSION BROKER"
        in text
    )
    assert "session_broker_mode" in text
    assert "session_broker_username" in text
    assert "managed_autologon" in text
    assert "configure-windows-gaming-session.ps1" in text


def test_template_contains_capability_but_not_broker_state():
    prep = (
        ROOT
        / "deploy"
        / "prepare-windows-gaming-template.ps1"
    ).read_text(encoding="utf-8")

    validate = (
        ROOT
        / "deploy"
        / "validate-windows-gaming-template.ps1"
    ).read_text(encoding="utf-8")

    assert "session-broker.json" in prep
    assert "session_broker_capability" in prep
    assert "session_broker_state_absent" in prep

    assert "session-broker.json" in validate
    assert "session_broker_capability_present" in validate
    assert "session_broker_state_absent" in validate


@pytest.mark.source_tree_only
def test_example_config_exposes_broker_policy():
    text = (
        ROOT / "config.example.yaml"
    ).read_text(encoding="utf-8")

    assert text.count("\ngaming:\n") == 1
    assert "session_broker_mode: existing" in text
    assert "session_broker_username: KhanGaming" in text


def test_managed_secret_not_embedded_in_template_scripts():
    for name in (
        "prepare-windows-gaming-template.ps1",
        "validate-windows-gaming-template.ps1",
    ):
        text = (
            ROOT / "deploy" / name
        ).read_text(encoding="utf-8")

        assert "LsaStorePrivateData" not in text
        assert "AutoAdminLogon" not in text
        assert "DefaultPassword" not in text


def test_installed_runtime_validation_excludes_source_tree_only_tests():
    installer = (
        ROOT / "deploy" / "install-runtime.ps1"
    ).read_text(encoding="utf-8")

    assert (
        '-m "not source_tree_only"'
        in installer
    )


def test_source_tree_only_marker_is_registered():
    pyproject = (
        ROOT / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert "source_tree_only:" in pyproject


def test_repository_layout_contracts_are_source_tree_only():
    vdd = (
        ROOT
        / "tests"
        / "test_vdd_runtime_policy_kg008k22.py"
    ).read_text(encoding="utf-8")

    current = Path(__file__).read_text(
        encoding="utf-8"
    )

    assert (
        "@pytest.mark.source_tree_only\n"
        "def test_vdd_runtime_policy_has_single_production_owner"
        in vdd
    )

    assert (
        "@pytest.mark.source_tree_only\n"
        "def test_example_config_exposes_broker_policy"
        in current
    )


def test_install_runtime_allows_config_already_at_installed_path():
    """A reinstall may receive config.yaml from its installed path."""
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "install-runtime.ps1"
    ).read_text()

    assert "$ConfigSourceFullPath" in script
    assert "$InstalledConfigFullPath" in script
    assert "$ConfigAlreadyInstalled" in script
    assert (
        "[System.StringComparison]::OrdinalIgnoreCase"
        in script
    )
    assert "if ($ConfigAlreadyInstalled)" in script
    assert (
        "Configuration source already matches installed target"
        in script
    )
    assert "Copy-Item $ConfigFile $InstalledConfig -Force" in script

