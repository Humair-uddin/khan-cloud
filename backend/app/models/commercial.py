from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class ProductCatalogItem(BaseModel):
    __tablename__="product_catalog_items"
    code:Mapped[str]=mapped_column(String(80),unique=True,index=True,nullable=False)
    workload_type:Mapped[str]=mapped_column(String(40),index=True,nullable=False)
    name:Mapped[str]=mapped_column(String(120),nullable=False)
    description:Mapped[str]=mapped_column(String(500),default="",nullable=False)
    currency:Mapped[str]=mapped_column(String(3),default="PKR",nullable=False)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True,index=True,nullable=False)
    is_sellable:Mapped[bool]=mapped_column(Boolean,default=False,index=True,nullable=False)
    metadata_json:Mapped[dict[str,Any]]=mapped_column(JSONB,default=dict)

class ProductRate(BaseModel):
    __tablename__="product_rates"
    product_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("product_catalog_items.id",ondelete="CASCADE"),index=True,nullable=False)
    dimension:Mapped[str]=mapped_column(String(60),index=True,nullable=False)
    unit:Mapped[str]=mapped_column(String(30),nullable=False)
    unit_price_minor:Mapped[int]=mapped_column(BigInteger,nullable=False)
    minimum_units:Mapped[int]=mapped_column(Integer,default=0,nullable=False)
    maximum_units:Mapped[int]=mapped_column(Integer,default=0,nullable=False)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True,index=True,nullable=False)

class CommercialQuote(BaseModel):
    __tablename__="commercial_quotes"
    organization_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("organizations.id",ondelete="RESTRICT"),index=True,nullable=False)
    user_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),index=True,nullable=False)
    product_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("product_catalog_items.id",ondelete="RESTRICT"),index=True,nullable=False)
    currency:Mapped[str]=mapped_column(String(3),nullable=False)
    billing_period:Mapped[str]=mapped_column(String(20),default="monthly",nullable=False)
    amount_minor:Mapped[int]=mapped_column(BigInteger,nullable=False)
    configuration:Mapped[dict[str,Any]]=mapped_column(JSONB,default=dict)
    pricing_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB,default=dict)
    status:Mapped[str]=mapped_column(String(30),default="quoted",index=True,nullable=False)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)

class CustomerOrder(BaseModel):
    __tablename__="customer_orders"
    organization_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("organizations.id",ondelete="RESTRICT"),index=True,nullable=False)
    user_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),index=True,nullable=False)
    quote_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("commercial_quotes.id",ondelete="RESTRICT"),unique=True,index=True,nullable=False)
    product_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("product_catalog_items.id",ondelete="RESTRICT"),index=True,nullable=False)
    currency:Mapped[str]=mapped_column(String(3),nullable=False)
    amount_minor:Mapped[int]=mapped_column(BigInteger,nullable=False)
    status:Mapped[str]=mapped_column(String(40),default="awaiting_payment",index=True,nullable=False)
    payment_status:Mapped[str]=mapped_column(String(40),default="awaiting_payment",index=True,nullable=False)
    payment_method:Mapped[str]=mapped_column(String(60),default="",nullable=False)
    configuration:Mapped[dict[str,Any]]=mapped_column(JSONB,default=dict)
    pricing_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB,default=dict)
    provisioning_authorization_id:Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True),ForeignKey("provisioning_authorizations.id",ondelete="RESTRICT"),nullable=True,index=True)
    vps_instance_id:Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True),ForeignKey("vps_instances.id",ondelete="SET NULL"),nullable=True,index=True)
    paid_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    provisioning_started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)

class PaymentAttempt(BaseModel):
    __tablename__="payment_attempts"
    order_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("customer_orders.id",ondelete="CASCADE"),index=True,nullable=False)
    method:Mapped[str]=mapped_column(String(60),index=True,nullable=False)
    status:Mapped[str]=mapped_column(String(40),default="pending",index=True,nullable=False)
    amount_minor:Mapped[int]=mapped_column(BigInteger,nullable=False)
    currency:Mapped[str]=mapped_column(String(3),nullable=False)
    provider_reference:Mapped[str]=mapped_column(String(160),default="",nullable=False)
    evidence_reference:Mapped[str]=mapped_column(String(255),default="",nullable=False)
    confirmed_by_user_id:Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),nullable=True,index=True)
    confirmed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
# ===== CATALOG / BILLING V2 =====
class ProductSKU(BaseModel):
    __tablename__ = "product_skus"
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_catalog_items.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    billing_mode: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    inventory_policy: Mapped[str] = mapped_column(String(30), default="none", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    is_sellable: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    metadata_json: Mapped[dict[str,Any]] = mapped_column(JSONB, default=dict)

class RegionalRate(BaseModel):
    __tablename__ = "regional_rates"
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_skus.id", ondelete="CASCADE"), index=True, nullable=False)
    region_code: Mapped[str] = mapped_column(String(16), default="GLOBAL", index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), index=True, nullable=False)
    billing_period: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    metering_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rate_kind: Mapped[str] = mapped_column(String(30), default="catalog", index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

class BillingWallet(BaseModel):
    __tablename__ = "billing_wallets"
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[UUID|None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), index=True, nullable=False)
    wallet_type: Mapped[str] = mapped_column(String(30), default="customer", index=True, nullable=False)
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    auto_recharge_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_recharge_threshold_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    auto_recharge_amount_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    low_balance_threshold_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    critical_balance_threshold_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

class WalletLedgerEntry(BaseModel):
    __tablename__ = "wallet_ledger_entries"
    wallet_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("billing_wallets.id", ondelete="RESTRICT"), index=True, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(60), default="", index=True, nullable=False)
    reference_id: Mapped[str] = mapped_column(String(120), default="", index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    metadata_json: Mapped[dict[str,Any]] = mapped_column(JSONB, default=dict)

class Promotion(BaseModel):
    __tablename__ = "promotions"
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(30), nullable=False)
    discount_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    region_code: Mapped[str] = mapped_column(String(16), default="GLOBAL", nullable=False)
    product_code: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    stackable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_redemptions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    starts_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

class PartnerAccount(BaseModel):
    __tablename__ = "partner_accounts"
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    partner_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(30), default="registered", nullable=False)
    wholesale_discount_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commission_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    settlement_currency: Mapped[str] = mapped_column(String(3), default="PKR", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True, nullable=False)

class PartnerEarning(BaseModel):
    __tablename__ = "partner_earnings"
    partner_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("partner_accounts.id", ondelete="RESTRICT"), index=True, nullable=False)
    earning_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    gross_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    earning_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True, nullable=False)
    available_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str,Any]] = mapped_column(JSONB, default=dict)

class Subscription(BaseModel):
    __tablename__ = "subscriptions"
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_skus.id", ondelete="RESTRICT"), index=True, nullable=False)
    billing_period: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True, nullable=False)
    next_bill_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class PaymentMethodToken(BaseModel):
    __tablename__ = "payment_method_tokens"
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    encrypted_provider_token: Mapped[str] = mapped_column(String(4096), nullable=False)
    encryption_key_version: Mapped[str] = mapped_column(String(40), nullable=False)
    token_fingerprint: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    display_label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True, nullable=False)

class UsageSession(BaseModel):
    __tablename__ = "usage_sessions"
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_skus.id", ondelete="RESTRICT"), index=True, nullable=False)
    wallet_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("billing_wallets.id", ondelete="RESTRICT"), index=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(30), default="khan_cloud", index=True, nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    per_minute_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_metered_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reason: Mapped[str] = mapped_column(String(80), default="", nullable=False)

class UsageCharge(BaseModel):
    __tablename__ = "usage_charges"
    usage_session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("usage_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class HostCapacityOffer(BaseModel):
    __tablename__ = "host_capacity_offers"
    node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), index=True, nullable=False)
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_skus.id", ondelete="CASCADE"), index=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(30), default="marketplace_host", index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    minimum_payout_per_hour_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    khan_cloud_payout_per_hour_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    availability_state: Mapped[str] = mapped_column(String(30), default="unavailable", index=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    metadata_json: Mapped[dict[str,Any]] = mapped_column(JSONB, default=dict)
