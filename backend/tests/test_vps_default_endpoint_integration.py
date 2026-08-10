from pathlib import Path


def test_successful_vps_create_reserves_default_ssh_endpoint():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "compute_service.py"
    ).read_text()

    assert "record_runtime_allocation(" in source
    assert "select_automatic_public_gateway(" in source
    assert "ensure_default_vps_port_mapping(" in source
    assert 'protocol="tcp"' in source
    assert "private_port=22" in source


def test_compute_does_not_reconcile_router_inline():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "compute_service.py"
    ).read_text()

    assert "reconcile_port_mapping_now" not in source
    assert "MikroTikRESTAdapter" not in source


def test_default_endpoint_helper_is_transaction_neutral():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "gateway_service.py"
    ).read_text()

    start = source.index(
        "def ensure_default_vps_port_mapping("
    )

    helper = source[start:]

    assert "db.commit()" not in helper


def test_endpoint_failure_does_not_invalidate_vps_completion():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "compute_service.py"
    ).read_text()

    assert "except GatewayError as exc:" in source
    assert "network.default_endpoint." in source
    assert "provisioning_failed" in source
    assert 'result="failure"' in source


def test_ipam_remains_outside_optional_endpoint_failure_boundary():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "compute_service.py"
    ).read_text()

    ipam = source.index("record_runtime_allocation(")
    gateway_try = source.index(
        "try:",
        ipam,
    )

    assert ipam < gateway_try
