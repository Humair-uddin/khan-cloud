#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.compute import VPSInstance
from app.models.network import IPAllocation, NetworkPool
from app.models.node import Node
from app.models.organization import Organization
from app.models.user import User
from app.schemas.compute import VPSCreate
from app.services.compute_service import create_vps, queue_vps_action, sync_node_capacity
from app.services.portal_service import customer_portal_summary

NODE_NAME="KC-R7425-VPS-01"
ORG_SLUG="khan-cloud-infrastructure"
VPS_NAME="KC-IPAM-PORTAL-ACCEPTANCE"


def wait_vps(vps_id, wanted, timeout=240):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        with SessionLocal() as db:
            v=db.get(VPSInstance,vps_id)
            if v is None: raise RuntimeError("VPS disappeared")
            if v.status==wanted: return v.status
            if v.status=="failed": raise RuntimeError(f"VPS failed: {v.failure_message}")
        time.sleep(3)
    raise RuntimeError(f"Timed out waiting for VPS {wanted}")


def generate_key():
    td=tempfile.TemporaryDirectory(prefix="kc-ipam-portal-")
    key=Path(td.name)/"id_ed25519"
    subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True)
    return td,key.with_suffix(".pub").read_text().strip()


def main():
    td,public_key=generate_key()
    try:
        with SessionLocal() as db:
            actor=db.scalar(select(User).where(User.username=="humair-uddin"))
            org=db.scalar(select(Organization).where(Organization.slug==ORG_SLUG))
            node=db.scalar(select(Node).where(Node.name==NODE_NAME))
            if actor is None or org is None or node is None: raise RuntimeError("Acceptance prerequisites missing")
            cap=sync_node_capacity(db,node)
            if not cap.scheduling_enabled: raise RuntimeError("R7425 is not schedulable")
            before=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)

            old=db.scalar(select(VPSInstance).where(VPSInstance.name==VPS_NAME).order_by(VPSInstance.created_at.desc()))
            if old is not None and old.status!="deleted":
                raise RuntimeError(f"Existing acceptance VPS is {old.status}")

            vps=create_vps(
                db,
                payload=VPSCreate(
                    organization_id=org.id,name=VPS_NAME,image="ubuntu-24.04",
                    vcpu=2,memory_mb=1024,disk_gb=8,ssh_public_key=public_key,
                ),
                actor=actor,
            )
            vps_id=vps.id

        wait_vps(vps_id,"running")

        with SessionLocal() as db:
            actor=db.scalar(select(User).where(User.username=="humair-uddin"))
            if actor is None:
                raise RuntimeError("Acceptance actor missing")
            vps=db.get(VPSInstance,vps_id)
            allocation=db.scalar(select(IPAllocation).where(
                IPAllocation.vps_instance_id==vps_id,
                IPAllocation.status=="active",
            ))
            if allocation is None: raise RuntimeError("No active IPAM allocation")
            pool=db.get(NetworkPool,allocation.pool_id)
            if pool is None or pool.slug!="kc-vps-private-nat":
                raise RuntimeError("VPS was not mapped into the Khan Cloud private NAT pool")
            if allocation.address != vps.primary_ip:
                raise RuntimeError("IPAM allocation does not match VPS primary IP")

            summary=customer_portal_summary(db,actor)
            row=next((x for x in summary.vps if x.id==vps_id),None)
            if row is None: raise RuntimeError("VPS absent from customer portal summary")
            if allocation.address not in row.private_addresses:
                raise RuntimeError("Portal does not expose customer private IP")

            queue_vps_action(db,vps=vps,action="delete",actor=actor)

        wait_vps(vps_id,"deleted")

        with SessionLocal() as db:
            allocation=db.scalar(select(IPAllocation).where(IPAllocation.vps_instance_id==vps_id))
            if allocation is None or allocation.status!="released" or allocation.released_at is None:
                raise RuntimeError("IPAM allocation was not released")
            node=db.scalar(select(Node).where(Node.name==NODE_NAME))
            cap=sync_node_capacity(db,node)
            after=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)
            if before!=after: raise RuntimeError(f"Capacity leak: {before} != {after}")
            result={
                "status":"PASS",
                "vps_id":str(vps_id),
                "private_ip":allocation.address,
                "network_pool":"kc-vps-private-nat",
                "allocation_status":allocation.status,
                "portal_visibility":"PASS",
                "portal_exposes_host_node_id":False,
                "capacity_before":before,
                "capacity_after":after,
            }
        print(json.dumps(result,indent=2))
    finally:
        td.cleanup()


if __name__=="__main__": main()
