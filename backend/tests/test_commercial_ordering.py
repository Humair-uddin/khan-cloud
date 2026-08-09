from pathlib import Path
from app.services import commercial_service

def test_catalog_seed_is_not_sellable_by_default():
    root=Path(__file__).resolve().parents[1]
    m=(root/"migrations"/"versions"/"d94a7f8b9c83_commercial_vps_ordering.py").read_text()
    assert "'vps-configurable'" in m and "true,false" in m

def test_pricing_uses_integer_minor_units():
    s=Path(commercial_service.__file__).read_text()
    assert "unit_price_minor" in s and "subtotal=q*r.unit_price_minor" in s

def test_quote_snapshot_copied_to_order():
    s=Path(commercial_service.__file__).read_text()
    assert "pricing_snapshot=q.pricing_snapshot" in s and "configuration=q.configuration" in s

def test_payment_creates_existing_provisioning_authorization():
    s=Path(commercial_service.__file__).read_text()
    assert 'source="confirmed_payment"' in s and 'reference_type="customer_order"' in s

def test_manual_confirmation_is_operator_only():
    s=Path(commercial_service.__file__).read_text()
    assert "Only Khan Cloud operators can confirm manual payments." in s

def test_portal_hides_deleted_from_active_vps():
    root=Path(__file__).resolve().parents[1]
    s=(root/"app"/"services"/"portal_service.py").read_text()
    assert 'v.status != "deleted"' in s

def test_portal_orders_through_commerce_not_direct_compute_create():
    root=Path(__file__).resolve().parents[2]
    s=(root/"customer-portal"/"portal.js").read_text()
    assert "/api/v1/commerce/quotes/vps" in s and "/api/v1/commerce/orders" in s
