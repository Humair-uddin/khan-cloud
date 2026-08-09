#!/usr/bin/env python3
import json,subprocess,tempfile,time
from pathlib import Path
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.commercial import CustomerOrder,ProductCatalogItem,ProductRate
from app.models.compute import VPSInstance
from app.models.node import Node
from app.models.user import User
from app.schemas.commercial import VPSQuoteCreate
from app.services.commercial_service import publish_vps_pricing,create_vps_quote,create_order,confirm_payment_and_provision
from app.services.compute_service import queue_vps_action,sync_node_capacity

NAME="KC-COMMERCIAL-ORDER-ACCEPTANCE"; NODE="KC-R7425-VPS-01"
def wait(vps_id,wanted,timeout=240):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        with SessionLocal() as db:
            v=db.get(VPSInstance,vps_id)
            if v and v.status==wanted:return
            if v and v.status=="failed":raise RuntimeError(v.failure_message)
        time.sleep(3)
    raise RuntimeError("timeout")

def main():
    td=tempfile.TemporaryDirectory(); key=Path(td.name)/"id"
    subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True); pub=key.with_suffix(".pub").read_text().strip()
    try:
        with SessionLocal() as db:
            u=db.scalar(select(User).where(User.username=="humair-uddin")); n=db.scalar(select(Node).where(Node.name==NODE))
            cap=sync_node_capacity(db,n); before=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)
            p=publish_vps_pricing(db,actor=u,cpu_minor=10000,memory_minor=5000,storage_minor=100)
            q=create_vps_quote(db,actor=u,payload=VPSQuoteCreate(name=NAME,image="ubuntu-24.04",vcpu=2,memory_gib=1,storage_gib=8,ssh_public_key=pub))
            expected=25800
            if q.amount_minor!=expected:raise RuntimeError("quote mismatch")
            o=create_order(db,actor=u,quote_id=q.id,payment_method="manual_bank")
            if o.vps_instance_id is not None:raise RuntimeError("unpaid order provisioned")
            oid=o.id
        with SessionLocal() as db:
            u=db.scalar(select(User).where(User.username=="humair-uddin"));o=confirm_payment_and_provision(db,actor=u,order_id=oid,provider_reference="ACCEPTANCE-ONLY");vid=o.vps_instance_id
        wait(vid,"running")
        with SessionLocal() as db:
            u=db.scalar(select(User).where(User.username=="humair-uddin"));v=db.get(VPSInstance,vid);queue_vps_action(db,vps=v,action="delete",actor=u)
        wait(vid,"deleted")
        with SessionLocal() as db:
            n=db.scalar(select(Node).where(Node.name==NODE));cap=sync_node_capacity(db,n);after=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)
            if before!=after:raise RuntimeError("capacity leak")
            o=db.get(CustomerOrder,oid);p=db.scalar(select(ProductCatalogItem).where(ProductCatalogItem.code=="vps-configurable"));p.is_sellable=False
            for r in db.scalars(select(ProductRate).where(ProductRate.product_id==p.id)).unique():r.is_active=False
            db.commit()
            print(json.dumps({"status":"PASS","quote_amount_minor":expected,"currency":"PKR","unpaid_provisioning_blocked":True,"payment_status":o.payment_status,"provisioning_authorization_id":str(o.provisioning_authorization_id),"vps_id":str(vid),"real_vps_lifecycle":"created_then_deleted","capacity_before":before,"capacity_after":after,"production_pricing_left_published":False},indent=2))
    finally:
        try:
            with SessionLocal() as db:
                product=db.scalar(select(ProductCatalogItem).where(ProductCatalogItem.code=="vps-configurable"))
                if product is not None:
                    product.is_sellable=False
                    for rate in db.scalars(select(ProductRate).where(ProductRate.product_id==product.id)).unique():
                        rate.is_active=False
                    db.commit()
        finally:
            td.cleanup()
if __name__=="__main__":main()
