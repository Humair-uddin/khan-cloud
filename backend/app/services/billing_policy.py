from __future__ import annotations

# ============================================================
# KHAN CLOUD COMMERCIAL POLICY V1
# ============================================================

PRICE_BOOK_VERSION = "2026.08-v1"

SUPPORTED_SETTLEMENT_CURRENCIES = {
    "PK": "PKR",
    "GLOBAL": "USD",
}

# ------------------------------------------------------------
# RESELLER / PARTNER POLICY
# ------------------------------------------------------------

RESELLER_TIERS = {
    "registered": {
        "wholesale_discount_bps": 1000,  # 10%
    },
    "silver": {
        "wholesale_discount_bps": 2000,  # 20%
    },
    "gold": {
        "wholesale_discount_bps": 3000,  # 30%
    },
    "platinum": {
        "wholesale_discount_bps": 4000,  # 40%
    },
    "strategic": {
        "wholesale_discount_bps": 5000,  # 50%
    },
}

MAX_RESELLER_WHOLESALE_DISCOUNT_BPS = 5000

# Example:
#
# List price       = 1000
# Strategic floor  = 500
# Customer discount= 30%
# Customer pays    = 700
# Reseller earns   = 200
# Khan Cloud floor = 500

PUBLIC_PROMO_MAX_BPS = 3000
REFERRAL_MAX_BPS = 1000
CELEBRITY_PROMO_MAX_BPS = 3000

# Public promotions are not automatically stacked with reseller
# wholesale economics.
DEFAULT_MAX_STACKED_CUSTOMER_DISCOUNT_BPS = 4000

# ------------------------------------------------------------
# HOST / MARKETPLACE POLICY
# ------------------------------------------------------------

HOST_PRICING_MODE = "khan_cloud_managed"

# Hosts may state a minimum acceptable payout, but Khan Cloud
# controls customer-facing retail pricing.
ALLOW_HOST_PUBLIC_PRICE_OVERRIDE = False

MINIMUM_KHAN_CLOUD_MARGIN_BPS = 1000

HOST_EARNING_CLEARING_DAYS = 7
RESELLER_EARNING_CLEARING_DAYS = 7
SETTLEMENT_CYCLE = "monthly"

# ------------------------------------------------------------
# WALLET POLICY
# ------------------------------------------------------------

WALLET_DEFAULTS = {
    "PKR": {
        "suggested_topups_minor": [
            50000,       # PKR 500
            100000,      # PKR 1,000
            500000,      # PKR 5,000
        ],
        "low_balance_minor": 20000,       # PKR 200
        "critical_balance_minor": 10000,  # PKR 100
        "auto_recharge_threshold_minor": 20000,
        "auto_recharge_amount_minor": 100000,
    },
    "USD": {
        "suggested_topups_minor": [
            1000,        # $10
            2500,        # $25
            5000,        # $50
        ],
        "low_balance_minor": 200,         # $2
        "critical_balance_minor": 100,    # $1
        "auto_recharge_threshold_minor": 200,
        "auto_recharge_amount_minor": 1000,
    },
}

METERED_MINIMUM_START_MINUTES = 5

# Customer-visible GPU/gaming rates are quoted hourly.
# Actual metering/charging is by minute.
METERED_RUNTIME_UNIT = "minute"

# When prepaid balance is exhausted:
# request stop/suspension of compute, DO NOT destroy persistent data.
ZERO_BALANCE_ACTION = "stop_compute_preserve_storage"

# ------------------------------------------------------------
# SUBSCRIPTION POLICY
# ------------------------------------------------------------

RECURRING_BILLING_PRODUCTS = {
    "vps",
    "storage",
    "snapshot",
    "dedicated_ipv4",
    "web_hosting",
    "gpu_dedicated",
}

PAYMENT_FAILURE_GRACE_DAYS = 3
SERVICE_SUSPENSION_AFTER_DAYS = 7
DATA_RETENTION_AFTER_SUSPENSION_DAYS = 30

# ------------------------------------------------------------
# GAMING
# ------------------------------------------------------------

FREE_GAMING_PROFILE_STORAGE_MIB = 2048

# This allocation is for Khan Cloud-managed profile metadata,
# logs/configuration and supported game-integration data.
# It is NOT general-purpose persistent game storage.

GAMING_PROFILE_STORAGE_PURPOSE = (
    "profile_metadata_logs_configuration"
)
