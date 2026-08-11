from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.commercial import (
    ProductCatalogItem,
    ProductSKU,
    RegionalRate,
)
from app.services.billing_policy import (
    FREE_GAMING_PROFILE_STORAGE_MIB,
    PRICE_BOOK_VERSION,
)


def minor_pkr(rupees: int | float) -> int:
    return int(
        (
            Decimal(str(rupees))
            * Decimal("100")
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def minor_usd(dollars: int | float) -> int:
    return int(
        (
            Decimal(str(dollars))
            * Decimal("100")
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def get_product(db, code: str) -> ProductCatalogItem:
    product = db.scalar(
        select(ProductCatalogItem).where(
            ProductCatalogItem.code == code
        )
    )

    if product is None:
        raise RuntimeError(
            f"STOP: product catalogue {code!r} is missing."
        )

    return product


def get_or_create_sku(
    db,
    *,
    product,
    code: str,
    name: str,
    billing_mode: str,
    inventory_policy: str,
    metadata: dict,
) -> ProductSKU:

    sku = db.scalar(
        select(ProductSKU).where(
            ProductSKU.code == code
        )
    )

    if sku is None:
        sku = ProductSKU(
            product_id=product.id,
            code=code,
            name=name,
            billing_mode=billing_mode,
            inventory_policy=inventory_policy,
            is_active=True,
            is_sellable=False,
            metadata_json=metadata,
        )
        db.add(sku)
        db.flush()
    else:
        sku.product_id = product.id
        sku.name = name
        sku.billing_mode = billing_mode
        sku.inventory_policy = inventory_policy
        sku.is_active = True

        # PRICE BOOK DOES NOT ACTIVATE INVENTORY.
        sku.is_sellable = False

        current = dict(sku.metadata_json or {})
        current.update(metadata)
        sku.metadata_json = current

    return sku


def upsert_rate(
    db,
    *,
    sku,
    region_code: str,
    currency: str,
    billing_period: str,
    metering_unit: str,
    amount_minor: int,
    active: bool = True,
) -> RegionalRate:

    rate = db.scalar(
        select(RegionalRate).where(
            RegionalRate.sku_id == sku.id,
            RegionalRate.region_code == region_code,
            RegionalRate.currency == currency,
            RegionalRate.billing_period == billing_period,
            RegionalRate.metering_unit == metering_unit,
            RegionalRate.rate_kind == "catalog",
        )
    )

    if rate is None:
        rate = RegionalRate(
            sku_id=sku.id,
            region_code=region_code,
            currency=currency,
            billing_period=billing_period,
            metering_unit=metering_unit,
            unit_price_minor=amount_minor,
            rate_kind="catalog",
            is_active=active,
        )
        db.add(rate)
    else:
        rate.unit_price_minor = amount_minor
        rate.is_active = active

    return rate


def add_subscription_prices(
    db,
    *,
    sku,
    monthly_pkr: int,
    monthly_usd: int | float,
    yearly_months: int = 10,
):
    upsert_rate(
        db,
        sku=sku,
        region_code="PK",
        currency="PKR",
        billing_period="monthly",
        metering_unit="subscription",
        amount_minor=minor_pkr(monthly_pkr),
    )

    upsert_rate(
        db,
        sku=sku,
        region_code="PK",
        currency="PKR",
        billing_period="yearly",
        metering_unit="subscription",
        amount_minor=minor_pkr(
            monthly_pkr * yearly_months
        ),
    )

    upsert_rate(
        db,
        sku=sku,
        region_code="GLOBAL",
        currency="USD",
        billing_period="monthly",
        metering_unit="subscription",
        amount_minor=minor_usd(monthly_usd),
    )

    upsert_rate(
        db,
        sku=sku,
        region_code="GLOBAL",
        currency="USD",
        billing_period="yearly",
        metering_unit="subscription",
        amount_minor=minor_usd(
            Decimal(str(monthly_usd))
            * Decimal(yearly_months)
        ),
    )


def add_metered_hourly_prices(
    db,
    *,
    sku,
    pkr_hour: int | float,
    usd_hour: int | float,
):
    # Customer sees the hourly price.
    # Usage engine charges corresponding minutes.

    upsert_rate(
        db,
        sku=sku,
        region_code="PK",
        currency="PKR",
        billing_period="hourly",
        metering_unit="minute",
        amount_minor=minor_pkr(pkr_hour),
    )

    upsert_rate(
        db,
        sku=sku,
        region_code="GLOBAL",
        currency="USD",
        billing_period="hourly",
        metering_unit="minute",
        amount_minor=minor_usd(usd_hour),
    )


def add_dedicated_prices(
    db,
    *,
    sku,
    pkr_hour: int | float,
    usd_hour: int | float,
):
    # Dedicated commitment pricing:
    # day   = 85% of 24h on-demand
    # month = 65% of 720h on-demand
    # year  = 10 monthly payments

    pkr_day = (
        Decimal(str(pkr_hour))
        * Decimal(24)
        * Decimal("0.85")
    )

    usd_day = (
        Decimal(str(usd_hour))
        * Decimal(24)
        * Decimal("0.85")
    )

    pkr_month = (
        Decimal(str(pkr_hour))
        * Decimal(720)
        * Decimal("0.65")
    )

    usd_month = (
        Decimal(str(usd_hour))
        * Decimal(720)
        * Decimal("0.65")
    )

    values = (
        (
            "PK",
            "PKR",
            "daily",
            minor_pkr(pkr_day),
        ),
        (
            "PK",
            "PKR",
            "monthly",
            minor_pkr(pkr_month),
        ),
        (
            "PK",
            "PKR",
            "yearly",
            minor_pkr(
                pkr_month * Decimal(10)
            ),
        ),
        (
            "GLOBAL",
            "USD",
            "daily",
            minor_usd(usd_day),
        ),
        (
            "GLOBAL",
            "USD",
            "monthly",
            minor_usd(usd_month),
        ),
        (
            "GLOBAL",
            "USD",
            "yearly",
            minor_usd(
                usd_month * Decimal(10)
            ),
        ),
    )

    for (
        region,
        currency,
        period,
        amount,
    ) in values:

        upsert_rate(
            db,
            sku=sku,
            region_code=region,
            currency=currency,
            billing_period=period,
            metering_unit="subscription",
            amount_minor=amount,
        )


def gpu_bundle(vram: int, gaming: bool) -> dict:

    if gaming:
        return {
            "included_vcpu": 8,
            "included_ram_gib": 32,
            "included_system_storage_gib": 40,
            "free_profile_storage_mib":
                FREE_GAMING_PROFILE_STORAGE_MIB,
            "persistent_game_storage":
                "optional_paid_addon",
            "billing_display": "hourly",
            "billing_charge": "per_minute",
        }

    if vram <= 16:
        cpu, ram, disk = 6, 24, 50
    elif vram <= 32:
        cpu, ram, disk = 8, 32, 75
    elif vram <= 48:
        cpu, ram, disk = 12, 64, 100
    else:
        cpu, ram, disk = 16, 96, 150

    return {
        "included_vcpu": cpu,
        "included_ram_gib": ram,
        "included_system_storage_gib": disk,
        "persistent_storage":
            "optional_paid_addon",
        "billing_display": "hourly",
        "billing_charge": "per_minute",
    }


VPS_PLANS = {
    "vps-nano": {
        "name": "KC Nano",
        "vcpu": 1,
        "ram_gib": 1,
        "storage_gib": 25,
        "pkr": 1999,
        "usd": 7,
    },
    "vps-starter": {
        "name": "KC Starter",
        "vcpu": 1,
        "ram_gib": 2,
        "storage_gib": 40,
        "pkr": 2799,
        "usd": 10,
    },
    "vps-standard": {
        "name": "KC Standard",
        "vcpu": 2,
        "ram_gib": 4,
        "storage_gib": 80,
        "pkr": 4499,
        "usd": 16,
    },
    "vps-business": {
        "name": "KC Business",
        "vcpu": 4,
        "ram_gib": 8,
        "storage_gib": 160,
        "pkr": 7999,
        "usd": 29,
    },
    "vps-pro": {
        "name": "KC Pro",
        "vcpu": 6,
        "ram_gib": 16,
        "storage_gib": 240,
        "pkr": 13999,
        "usd": 49,
    },
    "vps-power": {
        "name": "KC Power",
        "vcpu": 8,
        "ram_gib": 32,
        "storage_gib": 400,
        "pkr": 23999,
        "usd": 85,
    },
}


WEB_PLANS = {
    "webhosting-starter": {
        "name": "KC Web Starter",
        "pkr": 699,
        "usd": 3,
        "websites": 1,
        "storage_gib": 5,
    },
    "webhosting-business": {
        "name": "KC Web Business",
        "pkr": 1999,
        "usd": 7,
        "websites": 10,
        "storage_gib": 50,
    },
    "webhosting-professional": {
        "name": "KC Web Professional",
        "pkr": 3999,
        "usd": 14,
        "websites": 0,
        "storage_gib": 0,
    },
}


# These are customer-facing Khan Cloud LIST rates.
# They are not host payouts.
#
# Marketplace hosts may state minimum acceptable payouts;
# customer prices remain controlled by Khan Cloud.

GPU_AI = {
    "rtx-3080-10g": (10, 55, 0.20),
    "rtx-3090-24g": (24, 75, 0.28),
    "rtx-4090-24g": (24, 135, 0.49),
    "rtx-5070ti-16g": (16, 80, 0.29),
    "rtx-5080-16g": (16, 110, 0.39),
    "rtx-5090-32g": (32, 215, 0.79),

    "a6000-48g": (48, 135, 0.49),
    "l4-24g": (24, 135, 0.49),
    "l40s-48g": (48, 245, 0.89),
    "a100-80g": (80, 380, 1.39),
    "h100-80g": (80, 625, 2.29),
    "h200-141g": (141, 1030, 3.79),
    "b200-180g": (180, 1700, 6.25),
}


GPU_GAMING = {
    "rtx-3080-10g": (10, 70, 0.25),
    "rtx-3090-24g": (24, 95, 0.35),
    "rtx-4090-24g": (24, 165, 0.59),
    "rtx-5070ti-16g": (16, 105, 0.39),
    "rtx-5080-16g": (16, 140, 0.49),
    "rtx-5090-32g": (32, 260, 0.95),

    # Catalogued but normally not activated for gaming unless
    # explicitly supported by inventory/host capability.
    "a6000-48g": (48, 165, 0.59),
    "l4-24g": (24, 165, 0.59),
    "l40s-48g": (48, 290, 1.05),
    "a100-80g": (80, 435, 1.59),
    "h100-80g": (80, 705, 2.59),
    "h200-141g": (141, 1140, 4.19),
    "b200-180g": (180, 1850, 6.75),
}


with SessionLocal() as db:

    vps_catalog = get_product(
        db,
        "vps-configurable",
    )

    gpu_catalog = get_product(
        db,
        "gpu-catalog",
    )

    gaming_catalog = get_product(
        db,
        "gaming-catalog",
    )

    storage_catalog = get_product(
        db,
        "storage-catalog",
    )

    network_catalog = get_product(
        db,
        "network-catalog",
    )

    web_catalog = get_product(
        db,
        "webhosting-catalog",
    )

    # ========================================================
    # VPS
    # ========================================================

    for code, plan in VPS_PLANS.items():

        sku = get_or_create_sku(
            db,
            product=vps_catalog,
            code=code,
            name=plan["name"],
            billing_mode="subscription",
            inventory_policy="capacity",
            metadata={
                "price_book_version":
                    PRICE_BOOK_VERSION,
                "vcpu": plan["vcpu"],
                "ram_gib": plan["ram_gib"],
                "storage_gib":
                    plan["storage_gib"],
                "network_tier":
                    "shared_gateway",
                "dedicated_ipv4":
                    "optional_addon",
                "periods": [
                    "monthly",
                    "yearly",
                ],
            },
        )

        add_subscription_prices(
            db,
            sku=sku,
            monthly_pkr=plan["pkr"],
            monthly_usd=plan["usd"],
        )

    # ========================================================
    # STORAGE
    # ========================================================

    storage = get_or_create_sku(
        db,
        product=storage_catalog,
        code="storage-nvme",
        name="KC Persistent NVMe Storage",
        billing_mode="subscription",
        inventory_policy="capacity",
        metadata={
            "price_book_version":
                PRICE_BOOK_VERSION,
            "billing_quantity": "gib",
            "persistence": True,
        },
    )

    upsert_rate(
        db,
        sku=storage,
        region_code="PK",
        currency="PKR",
        billing_period="monthly",
        metering_unit="gib_month",
        amount_minor=minor_pkr(10),
    )

    upsert_rate(
        db,
        sku=storage,
        region_code="GLOBAL",
        currency="USD",
        billing_period="monthly",
        metering_unit="gib_month",
        amount_minor=minor_usd(0.04),
    )

    snapshot = get_or_create_sku(
        db,
        product=storage_catalog,
        code="snapshot-storage",
        name="KC Snapshot Storage",
        billing_mode="subscription",
        inventory_policy="capacity",
        metadata={
            "price_book_version":
                PRICE_BOOK_VERSION,
            "billing_quantity": "gib",
            "purpose":
                "point_in_time_disk_restore",
        },
    )

    upsert_rate(
        db,
        sku=snapshot,
        region_code="PK",
        currency="PKR",
        billing_period="monthly",
        metering_unit="gib_month",
        amount_minor=minor_pkr(5),
    )

    upsert_rate(
        db,
        sku=snapshot,
        region_code="GLOBAL",
        currency="USD",
        billing_period="monthly",
        metering_unit="gib_month",
        amount_minor=minor_usd(0.02),
    )

    profile = get_or_create_sku(
        db,
        product=storage_catalog,
        code="gaming-profile-storage-free",
        name="Gaming Profile Storage",
        billing_mode="included",
        inventory_policy="none",
        metadata={
            "price_book_version":
                PRICE_BOOK_VERSION,
            "included": True,
            "quota_mib":
                FREE_GAMING_PROFILE_STORAGE_MIB,
            "purpose":
                "gaming_profile_metadata_logs_configuration",
            "general_purpose_storage":
                False,
        },
    )

    # No paid regional rate:
    # it is an included gaming entitlement.

    # ========================================================
    # NETWORK
    # ========================================================

    ipv4 = get_or_create_sku(
        db,
        product=network_catalog,
        code="dedicated-ipv4",
        name="Dedicated Public IPv4",
        billing_mode="subscription",
        inventory_policy="inventory",
        metadata={
            "price_book_version":
                PRICE_BOOK_VERSION,
            "periods": ["monthly"],
        },
    )

    upsert_rate(
        db,
        sku=ipv4,
        region_code="PK",
        currency="PKR",
        billing_period="monthly",
        metering_unit="subscription",
        amount_minor=minor_pkr(500),
    )

    upsert_rate(
        db,
        sku=ipv4,
        region_code="GLOBAL",
        currency="USD",
        billing_period="monthly",
        metering_unit="subscription",
        amount_minor=minor_usd(2),
    )

    # ========================================================
    # WEB HOSTING
    # ========================================================

    for code, plan in WEB_PLANS.items():

        sku = get_or_create_sku(
            db,
            product=web_catalog,
            code=code,
            name=plan["name"],
            billing_mode="subscription",
            inventory_policy="capacity",
            metadata={
                "price_book_version":
                    PRICE_BOOK_VERSION,
                "websites": plan["websites"],
                "storage_gib":
                    plan["storage_gib"],
                "ssl": True,
                "periods": [
                    "monthly",
                    "yearly",
                ],
            },
        )

        add_subscription_prices(
            db,
            sku=sku,
            monthly_pkr=plan["pkr"],
            monthly_usd=plan["usd"],
        )

    # ========================================================
    # AI GPU
    # ========================================================

    for gpu_code, (
        vram,
        pkr_hour,
        usd_hour,
    ) in GPU_AI.items():

        sku_code = f"gpu-ai-{gpu_code}"

        sku = db.scalar(
            select(ProductSKU).where(
                ProductSKU.code == sku_code
            )
        )

        if sku is None:
            raise RuntimeError(
                f"STOP: seeded GPU SKU missing: {sku_code}"
            )

        sku.product_id = gpu_catalog.id
        sku.billing_mode = "metered"
        sku.inventory_policy = "inventory"
        sku.is_active = True
        sku.is_sellable = False

        metadata = dict(
            sku.metadata_json or {}
        )

        metadata.update(
            {
                "price_book_version":
                    PRICE_BOOK_VERSION,
                **gpu_bundle(
                    vram,
                    gaming=False,
                ),
            }
        )

        sku.metadata_json = metadata

        add_metered_hourly_prices(
            db,
            sku=sku,
            pkr_hour=pkr_hour,
            usd_hour=usd_hour,
        )

    # ========================================================
    # GAMING GPU + VM
    # ========================================================

    for gpu_code, (
        vram,
        pkr_hour,
        usd_hour,
    ) in GPU_GAMING.items():

        sku_code = f"gaming-{gpu_code}"

        sku = db.scalar(
            select(ProductSKU).where(
                ProductSKU.code == sku_code
            )
        )

        if sku is None:
            raise RuntimeError(
                f"STOP: gaming SKU missing: {sku_code}"
            )

        sku.product_id = gaming_catalog.id
        sku.billing_mode = "metered"
        sku.inventory_policy = "inventory"
        sku.is_active = True
        sku.is_sellable = False

        metadata = dict(
            sku.metadata_json or {}
        )

        metadata.update(
            {
                "price_book_version":
                    PRICE_BOOK_VERSION,
                **gpu_bundle(
                    vram,
                    gaming=True,
                ),
            }
        )

        sku.metadata_json = metadata

        add_metered_hourly_prices(
            db,
            sku=sku,
            pkr_hour=pkr_hour,
            usd_hour=usd_hour,
        )

    # ========================================================
    # DEDICATED GPU
    # ========================================================

    for gpu_code, (
        vram,
        pkr_hour,
        usd_hour,
    ) in GPU_AI.items():

        sku_code = (
            f"gpu-dedicated-{gpu_code}"
        )

        sku = db.scalar(
            select(ProductSKU).where(
                ProductSKU.code == sku_code
            )
        )

        if sku is None:
            raise RuntimeError(
                f"STOP: dedicated GPU SKU missing: "
                f"{sku_code}"
            )

        sku.product_id = gpu_catalog.id
        sku.billing_mode = "subscription"
        sku.inventory_policy = "inventory"
        sku.is_active = True
        sku.is_sellable = False

        metadata = dict(
            sku.metadata_json or {}
        )

        metadata.update(
            {
                "price_book_version":
                    PRICE_BOOK_VERSION,
                "included_vcpu":
                    gpu_bundle(
                        vram,
                        gaming=False,
                    )["included_vcpu"],
                "included_ram_gib":
                    gpu_bundle(
                        vram,
                        gaming=False,
                    )["included_ram_gib"],
                "included_system_storage_gib":
                    gpu_bundle(
                        vram,
                        gaming=False,
                    )[
                        "included_system_storage_gib"
                    ],
                "periods": [
                    "daily",
                    "monthly",
                    "yearly",
                ],
            }
        )

        sku.metadata_json = metadata

        add_dedicated_prices(
            db,
            sku=sku,
            pkr_hour=pkr_hour,
            usd_hour=usd_hour,
        )

    # ========================================================
    # FINAL SAFETY
    # ========================================================

    db.flush()

    # Price publication does NOT equal inventory activation.
    sellable = list(
        db.scalars(
            select(ProductSKU).where(
                ProductSKU.is_sellable.is_(True)
            )
        )
    )

    if sellable:
        raise RuntimeError(
            "STOP: Price Book V1 must not "
            "automatically activate SKUs: "
            + ", ".join(
                x.code for x in sellable
            )
        )

    db.commit()

    total_skus = len(
        list(
            db.scalars(
                select(ProductSKU)
            )
        )
    )

    total_rates = len(
        list(
            db.scalars(
                select(RegionalRate)
            )
        )
    )

    print(
        "========================================"
    )
    print(
        " KHAN CLOUD PRICE BOOK V1 APPLIED"
    )
    print(
        "========================================"
    )
    print(
        "price_book_version =",
        PRICE_BOOK_VERSION,
    )
    print(
        "total_skus         =",
        total_skus,
    )
    print(
        "regional_rates     =",
        total_rates,
    )
    print(
        "sellable_skus      = 0"
    )
    print(
        "inventory safety   = PASS"
    )
