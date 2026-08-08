#!/usr/bin/env python3
from __future__ import annotations
import json, time
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.compute import NodeCapacity, VPSInstance
from app.models.organization import Organization
from app.models.node import Node
from app.models.user import User
from app.schemas.compute import VPSCreate
from app.services.compute_service import create_vps, queue_vps_action, sync_node_capacity

NODE_NAME="KC-R7425-VPS-01"
ORG_SLUG="khan-cloud-infrastructure"
VPS_NAME="KC-FIRST-REAL-VPS"

def wait_vps(vps_id, wanted, timeout=150):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        with SessionLocal() as db:
            v=db.get(VPSInstance,vps_id)
            if v is None: raise RuntimeError("VPS disappeared")
            last=v.status
            if v.status==wanted:
                return {
                    "id":str(v.id),"status":v.status,"runtime_id":v.runtime_id,
                    "primary_ip":v.primary_ip,"node_id":str(v.node_id),
                }
            if v.status=="failed":
                raise RuntimeError(f"VPS failed: {v.failure_category}: {v.failure_message}")
        time.sleep(3)
    raise RuntimeError(f"Timed out waiting for {wanted}; last={last}")

def action(vps_id, name, wanted):
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.username=="humair-uddin"))
        v=db.get(VPSInstance,vps_id)
        queue_vps_action(db,vps=v,action=name,actor=actor)
    return wait_vps(vps_id,wanted)

def main():
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.username=="humair-uddin"))
        node=db.scalar(select(Node).where(Node.name==NODE_NAME))
        org=db.scalar(select(Organization).where(Organization.slug==ORG_SLUG))
        if actor is None or node is None or org is None: raise RuntimeError("Acceptance prerequisites missing")
        cap=sync_node_capacity(db,node)
        if not cap.scheduling_enabled:
            from app.services.compute_service import readiness_reasons
            raise RuntimeError(f"R7425 is not schedulable: {readiness_reasons(node,cap)}")
        before=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)

        existing=db.scalar(select(VPSInstance).where(VPSInstance.name==VPS_NAME).order_by(VPSInstance.created_at.desc()))
        if existing is not None and existing.status!="deleted":
            raise RuntimeError("Existing acceptance VPS is not deleted")

        vps=create_vps(
            db,
            payload=VPSCreate(
                organization_id=org.id,name=VPS_NAME,image="ubuntu-24.04",
                vcpu=2,memory_mb=1024,disk_gb=8,
            ),
            actor=actor,
        )
        vps_id=vps.id

    created=wait_vps(vps_id,"running",180)
    if not created["runtime_id"]: raise RuntimeError("Runtime ID missing after create")
    if not created["primary_ip"]: raise RuntimeError("Primary IP missing after create")

    stopped=action(vps_id,"stop","stopped")
    started=action(vps_id,"start","running")
    rebooted=action(vps_id,"reboot","running")
    deleted=action(vps_id,"delete","deleted")

    with SessionLocal() as db:
        node=db.scalar(select(Node).where(Node.name==NODE_NAME))
        cap=sync_node_capacity(db,node)
        after=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)
        if before != after:
            raise RuntimeError(f"Capacity leak after delete: before={before} after={after}")
        result={
            "status":"PASS",
            "vps_id":str(vps_id),
            "runtime_id":created["runtime_id"],
            "primary_ip":created["primary_ip"],
            "create":"running","stop":stopped["status"],"start":started["status"],
            "reboot":rebooted["status"],"delete":deleted["status"],
            "capacity_before":before,"capacity_after":after,
            "r7425_schedulable":cap.scheduling_enabled,
        }
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
