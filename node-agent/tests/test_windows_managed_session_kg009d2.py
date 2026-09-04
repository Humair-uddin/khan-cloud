import json
from pathlib import Path

import pytest

from khan_agent import windows_session_broker as broker


def test_broker_state_classifies_matching_account(
    monkeypatch,
    tmp_path,
):
    state = tmp_path / "session-broker.json"
    state.write_text(
        json.dumps(
            {
                "mode": "managed_autologon",
                "managed": True,
                "username": "KhanGaming",
            }
        ),
        encoding="utf-8",
    )

    class FakeTs:
        WTSUserName = 5
        WTSDomainName = 7

        @staticmethod
        def WTSGetActiveConsoleSessionId():
            return 4

        @staticmethod
        def WTSQuerySessionInformation(
            _server,
            _session,
            info,
        ):
            if info == FakeTs.WTSUserName:
                return "KhanGaming"
            return "KC-HOST"

    monkeypatch.setattr(
        broker.platform,
        "system",
        lambda: "Windows",
    )

    import sys

    monkeypatch.setitem(
        sys.modules,
        "win32ts",
        FakeTs,
    )

    session = broker.discover_interactive_session(
        state_path=state,
    )

    assert session.available is True
    assert session.session_id == 4
    assert session.managed is True
    assert session.source == "managed_console"
    assert session.username == "KC-HOST\\KhanGaming"
    assert session.broker_mode == "managed_autologon"


def test_managed_requirement_rejects_foreign_console(
    monkeypatch,
):
    monkeypatch.setattr(
        broker,
        "discover_interactive_session",
        lambda **kwargs: broker.InteractiveSession(
            session_id=3,
            available=True,
            source="active_console",
            managed=False,
            username="HOST\\OtherUser",
        ),
    )

    with pytest.raises(
        broker.WindowsSessionBrokerError,
        match="not broker-managed",
    ):
        broker.require_interactive_session(
            require_managed=True,
        )


def test_windows_configurator_uses_lsa_not_plaintext_registry():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    helper = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "windows-lsa-secret.ps1"
    ).read_text(encoding="utf-8")

    assert 'Store("DefaultPassword", password)' in helper
    assert "LsaStorePrivateData" in helper
    assert "POLICY_CREATE_SECRET" in helper
    assert "Remove-ItemProperty" in script
    assert '-Name "DefaultPassword"' in script

    # It must never write a DefaultPassword registry value.
    assert (
        'Set-ItemProperty `\n'
        '    -Path $Winlogon `\n'
        '    -Name "DefaultPassword"'
        not in script
    )


def test_windows_configurator_is_fail_closed_on_foreign_account():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert "Refusing to take ownership" in script
    assert "must not be a local administrator" in script
    assert "session-broker.json" in script
    assert '"kg009d2-v1"' in script


def test_gaming_config_exposes_session_broker_policy():
    from khan_agent.config import GamingConfig

    value = GamingConfig()

    assert value.session_broker_mode == "existing"
    assert value.session_broker_username == "KhanGaming"


def test_windows_configurator_has_explicit_deconfigure_path():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert '[ValidateSet("Configure", "Deconfigure")]' in script
    assert '$Action -eq "Deconfigure"' in script
    helper = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "windows-lsa-secret.ps1"
    ).read_text(encoding="utf-8")

    assert "ClearDefaultPassword" in script
    assert "LsaStorePrivateDataNull" in helper
    assert "IntPtr.Zero" in helper
    assert "AUTOADMINLOGON=DISABLED" in script
    assert "LSA_DEFAULTPASSWORD=REMOVED" in script
    assert "BROKER_STATE=REMOVED" in script
    assert "ACCOUNT_PRESERVED=" in script
    assert "Remove-LocalUser" not in script
    assert "Disable-LocalUser" not in script


def test_windows_configurator_validates_owned_state_contract():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert '$existingState.contract_version -eq "kg009d2-v1"' in script
    assert '$existingState.mode -eq "managed_autologon"' in script
    assert '$existingState.managed -eq $true' in script
    assert "not a valid " in script
    assert "managed-session ownership contract" in script
    assert "Refusing to deconfigure an unowned" in script


def test_windows_configurator_preserves_foreign_winlogon():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert "$ownsWinlogon" in script
    assert "$currentAutoUser -eq $ownedUser" in script
    assert "Refusing to modify Winlogon" in script
    assert "no longer " in script
    assert "owned by the Khan Cloud" in script


def test_runtime_installer_deconfigures_when_policy_is_not_managed():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "install-runtime.ps1"
    ).read_text(encoding="utf-8")

    assert "-Action Configure" in script
    assert "-Action Deconfigure" in script
    assert (
        "Windows gaming session broker deconfiguration failed."
        in script
    )


def test_deconfigure_is_safe_noop_without_owned_state():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert "BROKER_STATE=ABSENT" in script
    assert "AUTOADMINLOGON=UNCHANGED" in script
    assert "DECONFIGURATION=NOOP" in script


def test_managed_account_ownership_survives_deconfigure_for_reenable():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert '"session-broker-account.json"' in script
    assert '"kg009d2-account-v1"' in script
    assert "$accountIsOwned" in script
    assert "$AccountStatePath" in script
    assert "ACCOUNT_OWNERSHIP_STATE=PRESERVED" in script

    # Active autologon state is removed during Deconfigure.
    assert (
        'Remove-Item `\n'
        '        -Path $StatePath `'
        in script
    )

    # Durable account ownership proof must not be removed.
    assert (
        'Remove-Item `\n'
        '        -Path $AccountStatePath `'
        not in script
    )

    # Re-enable may reuse only a Khan-owned preserved account.
    assert (
        "$account -and\n"
        "    -not $stateIsOwned -and\n"
        "    -not $accountIsOwned"
        in script
    )

    # Foreign existing accounts still fail closed.
    assert "Refusing to take ownership" in script


def test_managed_account_marker_contains_no_password_material():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    marker_start = script.index(
        "$accountOwnership = [ordered]@{"
    )
    marker_end = script.index(
        "$accountOwnershipTemp",
        marker_start,
    )

    marker = script[marker_start:marker_end].lower()

    assert "password" not in marker
    assert "secret" not in marker


def test_broker_state_loader_accepts_utf8_bom(tmp_path):
    import json

    from khan_agent.windows_session_broker import load_broker_state

    state = tmp_path / "session-broker.json"

    payload = {
        "contract_version": "kg009d2-v1",
        "mode": "managed_autologon",
        "managed": True,
        "username": "KhanGaming",
    }

    state.write_bytes(
        b"\xef\xbb\xbf"
        + json.dumps(payload).encode("utf-8")
    )

    loaded = load_broker_state(state)

    assert loaded == payload


def test_broker_state_loader_accepts_bom_free_utf8(tmp_path):
    import json

    from khan_agent.windows_session_broker import load_broker_state

    state = tmp_path / "session-broker.json"

    payload = {
        "contract_version": "kg009d2-v1",
        "mode": "managed_autologon",
        "managed": True,
        "username": "KhanGaming",
    }

    state.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    assert load_broker_state(state) == payload


def test_broker_state_loader_fails_closed_for_malformed_json(
    tmp_path,
):
    from khan_agent.windows_session_broker import load_broker_state

    state = tmp_path / "session-broker.json"

    state.write_text(
        "{not-json",
        encoding="utf-8",
    )

    assert load_broker_state(state) == {}


def test_broker_state_loader_fails_closed_when_missing(tmp_path):
    from khan_agent.windows_session_broker import load_broker_state

    state = tmp_path / "missing-session-broker.json"

    assert load_broker_state(state) == {}


def test_managed_session_configurator_is_idempotent_for_owned_account():
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert 'Write-Host "ACCOUNT_PRESERVED=$UserName"' in script
    assert 'Write-Host "ACCOUNT_ROTATED=$UserName"' not in script

    assert "$credentialsChanged = $false" in script
    assert "if ($credentialsChanged)" in script

    assert (
        'Write-Host "REBOOT_REQUIRED_FOR_NEW_CONSOLE_SESSION=NO"'
        in script
    )


def test_managed_session_configurator_writes_bom_free_utf8_state():
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert "System.Text.UTF8Encoding($false)" in script
    assert "[System.IO.File]::WriteAllText(" in script

    broker_write_section = script[
        script.index("$stateJson = ("):
        script.index(
            'Write-Host "BROKER_STATE=$StatePath"'
        )
    ]

    assert "-Encoding UTF8" not in broker_write_section
