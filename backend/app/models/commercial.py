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
