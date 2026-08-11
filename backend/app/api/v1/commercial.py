from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.commercial import *
from app.services.commercial_service import *
from app.services.commercial_service import (
    _can_manage_commerce,
    _org,
)

router=APIRouter(prefix="/commerce",tags=["commerce"])

@router.get("/catalog",response_model=list[ProductCatalogRead])
def get_catalog(user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return [ProductCatalogRead(id=x["product"].id,code=x["product"].code,workload_type=x["product"].workload_type,name=x["product"].name,description=x["product"].description,currency=x["product"].currency,is_sellable=x["product"].is_sellable,metadata_json=x["product"].metadata_json,rates=[ProductRateRead.model_validate(r) for r in x["rates"]]) for x in catalog(db)]

@router.post("/quotes/vps",response_model=QuoteRead)
def quote_vps(payload:VPSQuoteCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    try:return create_vps_quote(db,actor=user,payload=payload)
    except CommercialError as e: raise HTTPException(status_code=400,detail=str(e))

@router.post("/orders",response_model=OrderRead)
def order(payload:OrderCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    try:return create_order(db,actor=user,quote_id=payload.quote_id,payment_method=payload.payment_method)
    except CommercialError as e: raise HTTPException(status_code=400,detail=str(e))

@router.get("/orders",response_model=list[OrderRead])
def orders(user:User=Depends(get_current_user),db:Session=Depends(get_db)): return visible_orders(db,user)

@router.post("/orders/{order_id}/payment-evidence",response_model=OrderRead)
def payment_evidence(order_id:UUID,payload:PaymentEvidenceCreate,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    try:return submit_payment_evidence(db,actor=user,order_id=order_id,evidence_reference=payload.evidence_reference,provider_reference=payload.provider_reference)
    except CommercialError as e: raise HTTPException(status_code=400,detail=str(e))

@router.post("/operator/pricing/vps")
def operator_publish_pricing(payload:OperatorPricingPublish,user:User=Depends(require_permission("commerce.manage")),db:Session=Depends(get_db)):
    try:
        p=publish_vps_pricing(db,actor=user,cpu_minor=payload.cpu_monthly_minor,memory_minor=payload.memory_gib_monthly_minor,storage_minor=payload.storage_gib_monthly_minor)
        return {"status":"published","product_id":str(p.id),"code":p.code}
    except CommercialError as e: raise HTTPException(status_code=400,detail=str(e))

@router.post("/operator/orders/{order_id}/confirm-payment",response_model=OrderRead)
def operator_confirm_payment(order_id:UUID,payload:PaymentConfirm,user:User=Depends(require_permission("commerce.manage")),db:Session=Depends(get_db)):
    try:return confirm_payment_and_provision(db,actor=user,order_id=order_id,provider_reference=payload.provider_reference)
    except CommercialError as e: raise HTTPException(status_code=400,detail=str(e))
# ===== CATALOG / BILLING V2 =====
@router.post("/operator/wallets/top-up",response_model=WalletRead)
def billing_wallet_topup(payload:WalletTopUpCreate,user:User=Depends(require_permission("commerce.manage")),db:Session=Depends(get_db)):
    try:return wallet_topup(db,actor=user,currency=payload.currency,amount_minor=payload.amount_minor,provider=payload.provider,provider_reference=payload.provider_reference)
    except CommercialError as e: raise HTTPException(status_code=400,detail=str(e))

@router.post("/operator/reseller/preview",response_model=ResellerPriceResult)
def billing_reseller_preview(payload:ResellerPricePreview,user:User=Depends(require_permission("commerce.manage"))):
    try:return reseller_price_preview(list_price_minor=payload.list_price_minor,wholesale_discount_bps=payload.wholesale_discount_bps,customer_discount_bps=payload.customer_discount_bps)
    except CommercialError as e: raise HTTPException(status_code=400,detail=str(e))
