from pathlib import Path
import base64
import pytest

from app.schemas.compute import VPSCreate
from app.services import compute_service


def test_image_catalog_is_explicit():
    images=compute_service.list_vps_images()
    assert [i.slug for i in images] == ["ubuntu-24.04"]
    assert images[0].access_username == "ubuntu"
    assert images[0].supports_cloud_init is True


def test_ssh_public_key_fingerprint_is_server_calculated():
    raw=b"x"*32
    key="ssh-ed25519 "+base64.b64encode(raw).decode()+" customer@test"
    normalized,fingerprint=compute_service._validate_ssh_public_key(key)
    assert normalized == key
    assert fingerprint.startswith("SHA256:")


def test_ssh_key_rejects_multiline_input():
    with pytest.raises(compute_service.ComputeError):
        compute_service._validate_ssh_public_key("ssh-ed25519 AAAA\nsecond-line")


def test_customer_provisioning_gate_text_is_present():
    source=Path(compute_service.__file__).read_text()
    assert "Provisioning authorization is required before customer resources can be reserved." in source
    assert 'source="operator"' in source


def test_secure_acceptance_requires_guest_ready_and_fingerprint():
    root=Path(__file__).resolve().parents[1]
    source=(root/"scripts"/"accept-secure-r7425-vps.py").read_text()
    assert '"guest_ready_at"' in source
    assert '"fingerprint"' in source
    assert "ssh-keygen" in source
