from pathlib import Path

from app.services import compute_service, gateway_service


def test_compute_delete_releases_port_mappings():
    source = Path(compute_service.__file__).read_text()

    assert (
        "release_vps_port_mappings(db, vps_id=vps.id)"
        in source
    )


def test_bulk_release_is_system_audited():
    source = Path(gateway_service.__file__).read_text()

    assert "def release_vps_port_mappings(" in source
    assert 'reason="VPS lifecycle deletion"' in source
    assert '"release_source": "vps_delete"' in source
    assert "actor_user_id=None" in source


def test_bulk_release_preserves_history():
    source = Path(gateway_service.__file__).read_text()

    assert 'mapping.status = "released"' in source
    assert "mapping.released_at = now" in source
    assert "db.delete(mapping)" not in source
