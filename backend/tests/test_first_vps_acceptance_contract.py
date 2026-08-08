from pathlib import Path

def test_acceptance_covers_full_real_vps_lifecycle():
    root=Path(__file__).resolve().parents[1]
    source=(root/"scripts"/"accept-first-r7425-vps.py").read_text()
    for token in ('"stop"','"start"','"reboot"','"delete"',"capacity_before","capacity_after"):
        assert token in source

def test_hypervisor_prepare_targets_only_existing_r7425():
    root=Path(__file__).resolve().parents[1]
    source=(root/"scripts"/"prepare-r7425-hypervisor.py").read_text()
    assert 'NODE_NAME="KC-R7425-VPS-01"' in source
    assert "pending_approval" in source
    assert "R7425 hypervisor activation" in source
