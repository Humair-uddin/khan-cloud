from pathlib import Path
from uuid import uuid4

from app.schemas.compute import GamingSessionCreate
from app.services import gaming_billing_service


def _read(relative: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / relative).read_text()


def test_currency_region_mapping_uses_server_policy():
    assert gaming_billing_service._region_for_currency("PKR") == "PK"
    assert gaming_billing_service._region_for_currency("USD") == "GLOBAL"


def test_play_request_id_is_backward_compatible_and_available_for_idempotency():
    legacy = GamingSessionCreate(name="legacy-session")
    assert legacy.play_request_id is None
    request_id = uuid4()
    modern = GamingSessionCreate(name="commercial-session", play_request_id=request_id)
    assert modern.play_request_id == request_id


def test_gaming_billing_uses_canonical_finance_wallet_not_legacy_billing_wallet():
    source = _read("app/services/gaming_billing_service.py")
    assert "CustomerWallet" in source
    assert "UsageReservation" in source
    assert "BillingWallet" not in source
    assert "reserve_funds(" in source
    assert "extend_reservation(" in source
    assert "release_reservation(" in source


def test_play_admission_is_price_book_driven_and_server_controlled():
    source = _read("app/services/gaming_billing_service.py")
    assert "ProductSKU" in source
    assert "RegionalRate" in source
    assert 'metadata.get("sku_code")' in source
    assert 'ProductSKU.is_sellable.is_(True)' in source
    assert 'RegionalRate.billing_period == "hourly"' in source
    assert 'RegionalRate.metering_unit == "minute"' in source
    assert "minute_rate_from_hourly" in source
    assert "METERED_MINIMUM_START_MINUTES" in source


def test_wallet_admission_serializes_concurrent_reservations():
    source = _read("app/services/wallet_service.py")
    reserve = source.split("def reserve_funds", 1)[1].split("def release_reservation", 1)[0]
    assert ".with_for_update()" in reserve
    assert '"Insufficient available wallet balance."' in reserve


def test_khan_owned_usage_does_not_create_synthetic_host_earning():
    source = _read("app/services/settlement_service.py")
    section = source.split("def consume_reserved_platform_usage", 1)[1]
    assert 'account_type="platform_revenue"' in section
    assert "HostEarning(" not in section


def test_marketplace_usage_requires_verified_host_offer():
    source = _read("app/services/gaming_billing_service.py")
    assert "HostCapacityOffer" in source
    assert 'HostCapacityOffer.availability_state == "available"' in source
    assert "HostCapacityOffer.is_verified.is_(True)" in source
    assert "host_payout_per_minute_minor" in source


def test_gaming_session_links_price_and_canonical_reservation():
    model = _read("app/models/compute.py")
    assert "product_sku_id" in model
    assert "usage_reservation_id" in model
    assert "pricing_snapshot" in model
    assert "per_minute_price_minor" in model
    assert "last_metered_at" in model
    assert "billing_finalized_at" in model


def test_duplicate_play_request_is_checked_before_new_placement():
    source = _read("app/services/gaming_service.py")
    duplicate = source.index("GamingSession.play_request_id == payload.play_request_id")
    placement = source.index("select_gaming_host(", duplicate)
    assert duplicate < placement


def test_heartbeat_reconciles_usage_and_can_request_stop():
    nodes = _read("app/api/v1/nodes.py")
    gaming = _read("app/services/gaming_service.py")
    assert "reconcile_gaming_billing_for_node" in nodes
    assert 'action="stop", commit=False' in gaming
    assert 'billing_stop_reason = "insufficient_wallet_balance"' in _read("app/services/gaming_billing_service.py")


def test_migration_is_additive_and_preserves_finance_parent():
    migration = _read("migrations/versions/c2a009f10001_gaming_commercial_runtime_v1.py")
    assert 'down_revision = "f2a002f10001"' in migration
    assert '"product_sku_id"' in migration
    assert '"usage_reservation_id"' in migration
    assert '"play_request_id"' in migration
    assert "usage_reservations" in migration
