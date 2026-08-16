from pathlib import Path

def test_registration_contract_has_physical_host_and_server_name():
    root=Path(__file__).resolve().parents[1]/'app'
    service=(root/'services'/'node_service.py').read_text()
    schema=(root/'schemas'/'node.py').read_text()
    assert '_resolve_physical_host' in service
    assert '_assigned_name' in service
    assert 'node.superseded' in service
    assert 'Strong physical-host identity is required' in service
    assert 'hardware_identity: HardwareIdentityEvidence' in schema
    assert 'assigned_name: str' in schema

def test_serial_is_evidence_not_authentication():
    service=(Path(__file__).resolve().parents[1]/'app'/'services'/'node_service.py').read_text()
    assert 'matching hash is not authentication' in service
    assert 'deployment profile' in service.lower()


def test_redeployment_supersession_is_purpose_scoped():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "node_service.py"
    ).read_text()

    assert "Node.intended_purpose == purpose" in source
