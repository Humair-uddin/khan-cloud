from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def test_windows_golden_template_scripts_exist():
    for name in (
        "prepare-windows-gaming-template.ps1",
        "validate-windows-gaming-template.ps1",
        "seal-proxmox-windows-gaming-template.sh",
    ):
        assert (DEPLOY / name).is_file()


def test_prepare_scrubs_clone_identity_and_credentials():
    src=(DEPLOY / "prepare-windows-gaming-template.ps1").read_text()
    for token in (
        "credentials.json",
        "identity.json",
        "deployment_enrollment_code",
        "control_plane_url",
        "Set-Service KhanCloudAgent -StartupType Manual",
        "kg006-v1",
    ):
        assert token in src


def test_validator_requires_runtime_qga_sunshine_and_blank_identity():
    src=(DEPLOY / "validate-windows-gaming-template.ps1").read_text()
    for token in (
        "qga_present",
        "sunshine_present",
        "credentials_absent",
        "identity_absent",
        "enrollment_placeholder_blank",
        "control_plane_placeholder_blank",
        "manifest_contract_valid",
    ):
        assert token in src


def test_sealer_validates_guest_before_template_conversion():
    src=(DEPLOY / "seal-proxmox-windows-gaming-template.sh").read_text()
    assert 'qm guest exec' in src
    assert 'qm template' in src
    assert 'khan-gaming-template-v1' in src
    assert src.index('qm guest exec') < src.index('qm template')
