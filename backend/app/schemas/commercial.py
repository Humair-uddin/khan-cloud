from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class ProductRateRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    dimension:str; unit:str; unit_price_minor:int; minimum_units:int; maximum_units:int

class ProductCatalogRead(BaseModel):
    id:UUID; code:str; workload_type:str; name:str; description:str; currency:str; is_sellable:bool
    metadata_json:dict[str,Any]; rates:list[ProductRateRead]=Field(default_factory=list)

class VPSQuoteCreate(BaseModel):
    product_code:str="vps-configurable"
    name:str=Field(min_length=2,max_length=100,pattern=r"^[A-Za-z0-9_.-]+$")
    image:str="ubuntu-24.04"; vcpu:int=Field(ge=1,le=128); memory_gib:int=Field(ge=1,le=1024); storage_gib:int=Field(ge=8,le=16384)
    network_tier:Literal["shared_gateway"]="shared_gateway"
    ssh_public_key:str=Field(min_length=40,max_length=4096)
    billing_period:Literal["monthly"]="monthly"

class QuoteRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID; product_id:UUID; currency:str; billing_period:str; amount_minor:int
    configuration:dict[str,Any]; pricing_snapshot:dict[str,Any]; status:str; expires_at:datetime

class OrderCreate(BaseModel):
    quote_id:UUID
    payment_method:Literal["manual_bank","manual_easypaisa","manual_jazzcash"]

class OrderRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID; quote_id:UUID; product_id:UUID; currency:str; amount_minor:int; status:str; payment_status:str; payment_method:str
    configuration:dict[str,Any]; provisioning_authorization_id:UUID|None; vps_instance_id:UUID|None
    paid_at:datetime|None; provisioning_started_at:datetime|None; created_at:datetime

class PaymentEvidenceCreate(BaseModel):
    evidence_reference:str=Field(min_length=3,max_length=255); provider_reference:str=Field(default="",max_length=160)

class PaymentConfirm(BaseModel):
    provider_reference:str=Field(default="",max_length=160)

class OperatorPricingPublish(BaseModel):
    cpu_monthly_minor:int=Field(gt=0); memory_gib_monthly_minor:int=Field(gt=0); storage_gib_monthly_minor:int=Field(gt=0)
# ===== CATALOG / BILLING V2 =====
class WalletTopUpCreate(BaseModel):
    currency: Literal["PKR","USD"]
    amount_minor: int = Field(gt=0)
    provider: str = Field(default="manual_bank", max_length=60)
    provider_reference: str = Field(default="", max_length=160)

class WalletRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID; currency:str; wallet_type:str; balance_minor:int
    auto_recharge_enabled:bool; auto_recharge_threshold_minor:int; auto_recharge_amount_minor:int
    low_balance_threshold_minor:int; critical_balance_threshold_minor:int

class ResellerPricePreview(BaseModel):
    list_price_minor:int=Field(gt=0)
    wholesale_discount_bps:int=Field(ge=0,le=9000)
    customer_discount_bps:int=Field(ge=0,le=9000)

class ResellerPriceResult(BaseModel):
    customer_charge_minor:int; khan_cloud_floor_minor:int; reseller_earning_minor:int
