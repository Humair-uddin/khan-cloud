from datetime import UTC,datetime,timedelta
from sqlalchemy import select
from app.models.commercial import CommercialQuote,CustomerOrder,PaymentAttempt,ProductCatalogItem,ProductRate
from app.models.compute import ProvisioningAuthorization
from app.schemas.compute import VPSCreate
from app.services.compute_service import create_vps
from app.services.organization_service import visible_organizations
from app.services.rbac_service import get_permission_codes

class CommercialError(ValueError): pass
RATE_DIMENSIONS=("vcpu","memory_gib","storage_gib")
def _can_manage_commerce(u):
    permissions=get_permission_codes(u)
    return "*" in permissions or "commerce.manage" in permissions
def _org(db,u):
    orgs=visible_organizations(db,u)
    if not orgs: raise CommercialError("No customer organization is available for this account.")
    return orgs[0].id
def _product(db,code):
    p=db.scalar(select(ProductCatalogItem).where(ProductCatalogItem.code==code))
    if p is None or not p.is_active: raise CommercialError("Product is unavailable.")
    return p
def catalog(db):
    ps=list(db.scalars(select(ProductCatalogItem).where(ProductCatalogItem.is_active.is_(True),ProductCatalogItem.is_sellable.is_(True))).unique())
    return [{"product":p,"rates":list(db.scalars(select(ProductRate).where(ProductRate.product_id==p.id,ProductRate.is_active.is_(True))).unique())} for p in ps]
def publish_vps_pricing(db,*,actor,cpu_minor,memory_minor,storage_minor):
    if not _can_manage_commerce(actor): raise CommercialError("Only Khan Cloud operators can publish pricing.")
    p=_product(db,"vps-configurable"); specs={"vcpu":("vCPU-month",cpu_minor,1,128),"memory_gib":("GiB-month",memory_minor,1,1024),"storage_gib":("GiB-month",storage_minor,8,16384)}
    existing={r.dimension:r for r in db.scalars(select(ProductRate).where(ProductRate.product_id==p.id)).unique()}
    for d,(unit,price,mn,mx) in specs.items():
        r=existing.get(d)
        if r is None: r=ProductRate(product_id=p.id,dimension=d,unit=unit,unit_price_minor=price); db.add(r)
        r.unit=unit; r.unit_price_minor=price; r.minimum_units=mn; r.maximum_units=mx; r.is_active=True
    p.is_sellable=True; db.commit(); db.refresh(p); return p
def create_vps_quote(db,*,actor,payload):
    p=_product(db,payload.product_code)
    if not p.is_sellable: raise CommercialError("This product has not been priced/published for sale.")
    rates={r.dimension:r for r in db.scalars(select(ProductRate).where(ProductRate.product_id==p.id,ProductRate.is_active.is_(True))).unique()}
    if any(d not in rates for d in RATE_DIMENSIONS): raise CommercialError("Product pricing is incomplete.")
    qty={"vcpu":payload.vcpu,"memory_gib":payload.memory_gib,"storage_gib":payload.storage_gib}; lines=[]; total=0
    for d in RATE_DIMENSIONS:
        r=rates[d]; q=qty[d]
        if q<r.minimum_units or (r.maximum_units and q>r.maximum_units): raise CommercialError(f"{d} is outside the sellable range.")
        subtotal=q*r.unit_price_minor; total+=subtotal; lines.append({"dimension":d,"quantity":q,"unit":r.unit,"unit_price_minor":r.unit_price_minor,"subtotal_minor":subtotal})
    q=CommercialQuote(organization_id=_org(db,actor),user_id=actor.id,product_id=p.id,currency=p.currency,billing_period=payload.billing_period,amount_minor=total,
      configuration={"name":payload.name,"image":payload.image,"vcpu":payload.vcpu,"memory_gib":payload.memory_gib,"storage_gib":payload.storage_gib,"network_tier":payload.network_tier,"ssh_public_key":payload.ssh_public_key},
      pricing_snapshot={"product_code":p.code,"product_name":p.name,"currency":p.currency,"billing_period":payload.billing_period,"lines":lines,"total_minor":total},
      status="quoted",expires_at=datetime.now(UTC)+timedelta(minutes=30))
    db.add(q);db.commit();db.refresh(q);return q
def create_order(db,*,actor,quote_id,payment_method):
    q=db.get(CommercialQuote,quote_id)
    if q is None or q.user_id!=actor.id: raise CommercialError("Quote not found.")
    if q.status!="quoted": raise CommercialError("Quote is no longer orderable.")
    ex=q.expires_at if q.expires_at.tzinfo else q.expires_at.replace(tzinfo=UTC)
    if ex<=datetime.now(UTC): q.status="expired";db.commit();raise CommercialError("Quote has expired.")
    o=CustomerOrder(organization_id=q.organization_id,user_id=actor.id,quote_id=q.id,product_id=q.product_id,currency=q.currency,amount_minor=q.amount_minor,status="awaiting_payment",payment_status="awaiting_payment",payment_method=payment_method,configuration=q.configuration,pricing_snapshot=q.pricing_snapshot)
    db.add(o);db.flush();db.add(PaymentAttempt(order_id=o.id,method=payment_method,status="pending",amount_minor=o.amount_minor,currency=o.currency));q.status="ordered";db.commit();db.refresh(o);return o
def submit_payment_evidence(db,*,actor,order_id,evidence_reference,provider_reference):
    o=db.get(CustomerOrder,order_id)
    if o is None or o.user_id!=actor.id: raise CommercialError("Order not found.")
    a=db.scalar(select(PaymentAttempt).where(PaymentAttempt.order_id==o.id).order_by(PaymentAttempt.created_at.desc()))
    if a is None: raise CommercialError("Payment attempt is missing.")
    a.evidence_reference=evidence_reference;a.provider_reference=provider_reference;a.status="evidence_submitted";o.payment_status="evidence_submitted";o.status="payment_review";db.commit();db.refresh(o);return o
def confirm_payment_and_provision(db,*,actor,order_id,provider_reference=""):
    if not _can_manage_commerce(actor): raise CommercialError("Only Khan Cloud operators can confirm manual payments.")
    o=db.get(CustomerOrder,order_id)
    if o is None: raise CommercialError("Order not found.")
    if o.vps_instance_id is not None: return o
    if o.payment_status not in {"awaiting_payment","evidence_submitted"}: raise CommercialError("Order is not confirmable.")
    a=db.scalar(select(PaymentAttempt).where(PaymentAttempt.order_id==o.id).order_by(PaymentAttempt.created_at.desc()))
    now=datetime.now(UTC); a.status="confirmed"; a.provider_reference=provider_reference or a.provider_reference; a.confirmed_by_user_id=actor.id; a.confirmed_at=now
    o.payment_status="confirmed";o.status="payment_confirmed";o.paid_at=now
    auth=ProvisioningAuthorization(organization_id=o.organization_id,created_by_user_id=actor.id,source="confirmed_payment",status="authorized",reference_type="customer_order",reference_id=str(o.id),expires_at=now+timedelta(hours=1))
    db.add(auth);db.flush();o.provisioning_authorization_id=auth.id;db.commit();db.refresh(o)
    c=o.configuration
    v=create_vps(db,payload=VPSCreate(organization_id=o.organization_id,provisioning_authorization_id=auth.id,name=c["name"],image=c["image"],vcpu=int(c["vcpu"]),memory_mb=int(c["memory_gib"])*1024,disk_gb=int(c["storage_gib"]),ssh_public_key=c["ssh_public_key"]),actor=actor)
    o=db.get(CustomerOrder,o.id);o.vps_instance_id=v.id;o.status="provisioning";o.provisioning_started_at=datetime.now(UTC);db.commit();db.refresh(o);return o
def visible_orders(db,u):
    rows=list(db.scalars(select(CustomerOrder).order_by(CustomerOrder.created_at.desc())).unique())
    return rows if _can_manage_commerce(u) else [x for x in rows if x.user_id==u.id]
# ===== CATALOG / BILLING V2 =====
def minute_rate_from_hourly(hourly_minor:int)->int:
    if hourly_minor<=0: raise CommercialError("Hourly price must be positive.")
    return max(1,(hourly_minor+30)//60)

def reseller_price_preview(*,list_price_minor:int,wholesale_discount_bps:int,customer_discount_bps:int)->dict:
    if customer_discount_bps>wholesale_discount_bps:
        raise CommercialError("Customer discount cannot exceed reseller wholesale discount.")
    floor=list_price_minor*(10000-wholesale_discount_bps)//10000
    charge=list_price_minor*(10000-customer_discount_bps)//10000
    return {"customer_charge_minor":charge,"khan_cloud_floor_minor":floor,"reseller_earning_minor":max(0,charge-floor)}

def calculate_marketplace_split(*,customer_charge_minor:int,host_payout_minor:int=0,reseller_earning_minor:int=0,payment_cost_minor:int=0,minimum_khan_margin_minor:int=0)->dict:
    margin=customer_charge_minor-host_payout_minor-reseller_earning_minor-payment_cost_minor
    if margin<minimum_khan_margin_minor:
        raise CommercialError("Transaction violates Khan Cloud minimum margin floor.")
    return {"customer_charge_minor":customer_charge_minor,"host_payout_minor":host_payout_minor,"reseller_earning_minor":reseller_earning_minor,"payment_cost_minor":payment_cost_minor,"khan_cloud_margin_minor":margin}

def get_or_create_wallet(db,*,actor,currency:str):
    from app.models.commercial import BillingWallet
    org_id=_org(db,actor)
    w=db.scalar(select(BillingWallet).where(BillingWallet.organization_id==org_id,BillingWallet.currency==currency,BillingWallet.wallet_type=="customer"))
    if w is None:
        w=BillingWallet(organization_id=org_id,user_id=actor.id,currency=currency,wallet_type="customer",balance_minor=0)
        db.add(w);db.commit();db.refresh(w)
    return w

def wallet_topup(db,*,actor,currency:str,amount_minor:int,provider:str,provider_reference:str=""):
    from app.models.commercial import WalletLedgerEntry
    w=get_or_create_wallet(db,actor=actor,currency=currency)
    w.balance_minor+=amount_minor
    e=WalletLedgerEntry(wallet_id=w.id,entry_type="topup",amount_minor=amount_minor,balance_after_minor=w.balance_minor,reference_type="payment_provider",reference_id=provider_reference,description=f"Wallet top-up via {provider}")
    db.add(e);db.commit();db.refresh(w);return w
