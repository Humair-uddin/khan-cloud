from pathlib import Path


def test_compute_api_exposes_host_and_vps_surfaces():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "api" / "v1" / "compute.py").read_text()
    assert '"/hosts"' in source
    assert '"/vps"' in source
    assert '"/vps/{vps_id}/actions"' in source
    assert 'require_permission("compute.hosts.read")' in source
    assert 'require_permission("vps.manage")' in source


def test_node_runtime_uses_node_credentials_not_ssh():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "api" / "v1" / "node_runtime.py").read_text()
    assert "get_authenticated_node" in source
    assert '"/jobs/next"' in source
    assert '"/jobs/{job_id}/result"' in source
    assert "ssh" not in source.lower()


def test_customer_role_does_not_receive_host_inventory_permission():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "services" / "rbac_service.py").read_text()
    customer = source.split('"customer":', 1)[1].split('"viewer":', 1)[0]
    assert '"vps.read"' in customer
    assert '"vps.manage"' in customer
    assert '"compute.hosts.read"' not in customer
