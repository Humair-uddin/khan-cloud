from pathlib import Path

import pytest
import yaml

from khan_agent.config import AgentSettings
import khan_agent.windows_protected_secret as protected


ROOT = Path(__file__).resolve().parents[1]


def base_config() -> dict:
    return {
        "agent": {
            "node_name": "test-node",
            "control_plane_url": "https://control.invalid",
            "observation_only": False,
        },
        "gaming": {
            "enabled": True,
            "execution_backend": "windows_native",
            "streaming_backend": "sunshine",
        },
    }


def test_windows_lsa_source_hydrates_only_in_memory(
    tmp_path,
    monkeypatch,
):
    config = base_config()

    config["gaming"].update(
        {
            "sunshine_api_username": "KhanCloud",
            "sunshine_credential_source": "windows_lsa",
            "sunshine_secret_name":
                "KhanCloudSunshineApiPassword",
        }
    )

    path = tmp_path / "config.yaml"

    path.write_text(
        yaml.safe_dump(
            config,
            sort_keys=False,
        )
    )

    monkeypatch.setattr(
        protected,
        "read_windows_protected_secret",
        lambda secret_name, required=True:
            "protected-test-value",
    )

    settings = AgentSettings.load(path)

    assert (
        settings.gaming.sunshine_api_password
        == "protected-test-value"
    )

    assert (
        settings.gaming.sunshine_secret_name
        == "KhanCloudSunshineApiPassword"
    )

    dumped = settings.model_dump()

    assert (
        "sunshine_api_password"
        not in dumped["gaming"]
    )

    on_disk = yaml.safe_load(
        path.read_text()
    )

    assert (
        "sunshine_api_password"
        not in on_disk["gaming"]
    )


def test_windows_lsa_rejects_plaintext_password(
    tmp_path,
):
    config = base_config()

    config["gaming"].update(
        {
            "sunshine_api_username": "KhanCloud",
            "sunshine_credential_source": "windows_lsa",
            "sunshine_api_password":
                "plaintext-must-be-rejected",
        }
    )

    path = tmp_path / "config.yaml"

    path.write_text(
        yaml.safe_dump(
            config,
            sort_keys=False,
        )
    )

    with pytest.raises(
        ValueError,
        match="must not contain plaintext",
    ):
        AgentSettings.load(path)


def test_legacy_config_source_remains_injectable(
    tmp_path,
):
    config = base_config()

    config["gaming"].update(
        {
            "sunshine_api_username": "admin",
            "sunshine_credential_source": "config",
            "sunshine_api_password":
                "unit-test-secret",
        }
    )

    path = tmp_path / "config.yaml"

    path.write_text(
        yaml.safe_dump(
            config,
            sort_keys=False,
        )
    )

    settings = AgentSettings.load(path)

    assert (
        settings.gaming.sunshine_api_password
        == "unit-test-secret"
    )


def test_shared_lsa_helper_has_generic_contract():
    text = (
        ROOT /
        "deploy" /
        "windows-lsa-secret.ps1"
    ).read_text(encoding="utf-8")

    assert "LsaStorePrivateData" in text
    assert "LsaRetrievePrivateData" in text
    assert "LsaFreeMemory" in text

    assert "public static void Store(" in text
    assert "public static string Retrieve(" in text
    assert "public static void Delete(" in text

    # KG-009D2 compatibility remains.
    assert "StoreDefaultPassword" in text
    assert "ClearDefaultPassword" in text


def test_managed_session_uses_shared_lsa_helper():
    text = (
        ROOT /
        "deploy" /
        "configure-windows-gaming-session.ps1"
    ).read_text(encoding="utf-8")

    assert "windows-lsa-secret.ps1" in text

    assert (
        "[KhanLsaSecret]::StoreDefaultPassword"
        in text
    )

    assert (
        "[KhanLsaSecret]::ClearDefaultPassword"
        in text
    )


def test_sunshine_provisioner_is_idempotent():
    text = (
        ROOT /
        "deploy" /
        "configure-windows-sunshine.ps1"
    ).read_text(encoding="utf-8")

    assert "[KhanLsaSecret]::Retrieve" in text
    assert "[KhanLsaSecret]::Store" in text
    assert "--creds" in text

    assert "repair_required" in text

    assert (
        "SUNSHINE_CREDENTIAL_PRESERVED=YES"
        in text
    )

    assert (
        "SUNSHINE_CREDENTIAL_ROTATED=NO"
        in text
    )

    assert "SECRET_VALUE_PRINTED=NO" in text
    assert "Restart-Computer" not in text


def test_sunshine_restart_is_conditional_not_unconditional():
    text = (
        ROOT /
        "deploy" /
        "configure-windows-sunshine.ps1"
    ).read_text(encoding="utf-8")

    assert "if (-not $ready)" in text
    assert "Restart-Service" in text

    restart = text.index("Restart-Service")
    post_credential_probe = text.index(
        "$sunshineServiceRestarted = $false"
    )

    assert post_credential_probe < restart

    assert (
        "SUNSHINE_SERVICE_RESTARTED=YES"
        in text
    )

    assert (
        "SUNSHINE_SERVICE_RESTARTED=NO"
        in text
    )

def test_sunshine_nonvalidating_tls_probe_uses_bounded_python_stdin():
    from pathlib import Path

    text = Path(
        "deploy/configure-windows-sunshine.ps1"
    ).read_text(encoding="utf-8")

    assert '[string]$PythonPath = ""' in text
    assert '[string]$PythonExecutable = ""' in text
    assert "ssl._create_unverified_context()" in text
    compact = " ".join(text.split())
    assert "RedirectStandardInput = $true" in compact
    assert "$process.StandardInput.Write( $payload )" in compact
    assert "$process.WaitForExit( 15000 )" in compact
    assert "$process.Kill()" in compact
    assert "-PythonExecutable $PythonPath" in text

    # The protected password must not be placed in the
    # Python process command line.
    assert (
        "$startInfo.Arguments = $ApiPassword"
        not in text
    )
    assert (
        "$startInfo.Arguments = "
        '"$ApiPassword"'
        not in text
    )


def test_installer_hands_runtime_python_to_sunshine_configurator():
    from pathlib import Path

    text = Path(
        "deploy/install-runtime.ps1"
    ).read_text(encoding="utf-8")

    sunshine = text.index(
        "===== CONFIGURE SUNSHINE PROTECTED CREDENTIAL ====="
    )

    enrollment = text.index(
        "# ENROLLMENT"
    )

    block = text[sunshine:enrollment]

    assert '"-PythonPath"' in block
    assert "$Python" in block
