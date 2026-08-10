from pathlib import Path
from types import SimpleNamespace

from app.services import network_service


class FakeScalars:
    def __init__(self, rows): self.rows=rows
    def unique(self): return self
    def __iter__(self): return iter(self.rows)


def test_pool_matching_uses_cidr(monkeypatch):
    pool=SimpleNamespace(cidr="192.168.250.0/24")
    monkeypatch.setattr(network_service,"list_network_pools",lambda db:[pool])
    assert network_service._pool_for_address(object(),"192.168.250.205") is pool
    assert network_service._pool_for_address(object(),"10.10.10.5") is None


def test_private_nat_pool_is_seeded_without_public_routing():
    root=Path(__file__).resolve().parents[1]
    migration=(root/"migrations"/"versions"/"c83f6e7a8b72_vps_network_ipam.py").read_text()
    assert '"network_type": "private_nat"' in migration
    assert '"cidr": "192.168.250.0/24"' in migration
    assert "externally_routable" in migration
    assert "true,true,false" in migration


def test_compute_lifecycle_records_and_releases_ipam():
    from app.services import compute_service
    source=Path(compute_service.__file__).read_text()
    assert "record_runtime_allocation(" in source
    assert "vps=vps" in source
    assert "address=vps.primary_ip" in source
    assert "release_vps_addresses(db, vps_id=vps.id)" in source


def test_customer_portal_schema_never_exposes_host_node_id():
    root=Path(__file__).resolve().parents[1]
    schema=(root/"app"/"schemas"/"portal.py").read_text()
    assert "node_id" not in schema
    assert "private_addresses" in schema
    assert "public_addresses" in schema


def test_customer_portal_create_is_payment_gated_in_ui():
    root=Path(__file__).resolve().parents[2]
    html=(root/"customer-portal"/"index.html").read_text()
    js=(root/"customer-portal"/"portal.js").read_text()

    # Create VPS is enabled only through the commerce quote/order path.
    assert 'id="new-vps"' in html
    assert "/api/v1/commerce/quotes/vps" in js
    assert "/api/v1/commerce/orders" in js
    assert 'post("/api/v1/compute/vps"' not in js
    assert "payment" in html.lower()


def test_customer_portal_is_separate_static_surface():
    root=Path(__file__).resolve().parents[1]
    main=(root/"app"/"main.py").read_text()
    assert '"/portal"' in main
    assert "CUSTOMER_PORTAL_DIR" in main
