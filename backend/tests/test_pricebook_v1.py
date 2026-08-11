from pathlib import Path

from app.services.billing_policy import (
    ALLOW_HOST_PUBLIC_PRICE_OVERRIDE,
    MAX_RESELLER_WHOLESALE_DISCOUNT_BPS,
    METERED_RUNTIME_UNIT,
    RESELLER_TIERS,
    ZERO_BALANCE_ACTION,
)


def test_host_does_not_control_public_price():
    assert ALLOW_HOST_PUBLIC_PRICE_OVERRIDE is False


def test_strategic_reseller_supports_50_percent_floor():
    assert (
        RESELLER_TIERS[
            "strategic"
        ]["wholesale_discount_bps"]
        == 5000
    )

    assert (
        MAX_RESELLER_WHOLESALE_DISCOUNT_BPS
        == 5000
    )


def test_gpu_usage_is_charged_per_minute():
    assert METERED_RUNTIME_UNIT == "minute"


def test_zero_balance_preserves_storage():
    assert (
        ZERO_BALANCE_ACTION
        == "stop_compute_preserve_storage"
    )


def test_pricebook_seed_preserves_inventory_gating():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "scripts"
        / "seed_pricebook_v1.py"
    ).read_text()

    assert "sku.is_sellable = False" in source
    assert "sellable_skus      = 0" in source


def test_pricebook_contains_required_products():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "scripts"
        / "seed_pricebook_v1.py"
    ).read_text()

    required = (
        "vps-nano",
        "vps-starter",
        "vps-standard",
        "vps-business",
        "vps-pro",
        "vps-power",
        "storage-nvme",
        "snapshot-storage",
        "gaming-profile-storage-free",
        "dedicated-ipv4",
        "webhosting-starter",
        "webhosting-business",
        "webhosting-professional",
    )

    for code in required:
        assert code in source
