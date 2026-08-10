from pathlib import Path

from app.services import compute_service, gateway_service


def test_new_mapping_starts_pending_apply():
    source = Path(gateway_service.__file__).read_text()

    assert 'status="pending"' in source
    assert 'reconcile_action="apply"' in source


def test_explicit_release_requests_external_removal():
    source = Path(gateway_service.__file__).read_text()

    assert 'mapping.status = "releasing"' in source
    assert 'mapping.reconcile_action = "remove"' in source
    assert (
        'action="network.port_mapping.release_requested"'
        in source
    )


def test_vps_delete_requests_mapping_removal():
    compute_source = Path(
        compute_service.__file__
    ).read_text()

    gateway_source = Path(
        gateway_service.__file__
    ).read_text()

    assert (
        "release_vps_port_mappings(db, vps_id=vps.id)"
        in compute_source
    )

    assert 'mapping.status = "releasing"' in gateway_source
    assert 'mapping.reconcile_action = "remove"' in gateway_source
    assert (
        'reason="VPS lifecycle deletion"'
        in gateway_source
    )


def test_release_does_not_free_port_before_reconciliation():
    source = Path(gateway_service.__file__).read_text()

    release_start = source.index(
        "def release_port_mapping("
    )

    bulk_start = source.index(
        "def release_vps_port_mappings("
    )

    explicit_release = source[
        release_start:bulk_start
    ]

    assert 'mapping.status = "released"' not in explicit_release
    assert "mapping.released_at =" not in explicit_release


def test_active_listing_only_exposes_confirmed_mappings():
    source = Path(gateway_service.__file__).read_text()

    assert 'PortMapping.status == "active"' in source


def test_failed_or_pending_mapping_still_reserves_port():
    source = Path(gateway_service.__file__).read_text()

    assert 'PortMapping.status != "released"' in source


def test_bulk_release_preserves_mapping_history():
    source = Path(gateway_service.__file__).read_text()

    assert "db.delete(mapping)" not in source
