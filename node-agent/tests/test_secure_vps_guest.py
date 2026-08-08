from pathlib import Path
from khan_agent import virtualization as virt


def test_cloud_init_disables_password_ssh_and_injects_key(tmp_path):
    user,meta=virt._write_cloud_init(
        tmp_path,"kc-test",access_username="ubuntu",
        ssh_public_key="ssh-ed25519 AAAATEST test@example",
    )
    text=user.read_text()
    assert "ssh_pwauth: false" in text
    assert "disable_root: true" in text
    assert "ssh-ed25519 AAAATEST test@example" in text
    assert "ubuntu" in text
    assert meta.exists()


def test_create_requires_ssh_public_key():
    source=Path(virt.__file__).read_text()
    assert "SSH public key is required for secure VPS provisioning." in source


def test_create_waits_for_guest_ssh_readiness():
    source=Path(virt.__file__).read_text()
    assert "_wait_tcp(ip, 22" in source
    assert "VPS guest did not become SSH-ready." in source


def test_success_result_reports_guest_ready():
    source=Path(virt.__file__).read_text()
    assert '"guest_ready": True' in source
    assert '"access_username": access_username' in source
