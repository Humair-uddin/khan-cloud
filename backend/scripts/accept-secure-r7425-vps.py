#!/usr/bin/env python3
from __future__ import annotations
import json
import subprocess
import tempfile
import time
from pathlib import Path
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
VPS_NAME="KC-SECURE-PROVISIONING-TEST"

def wait_vps(vps_id, wanted, timeout=240):
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
                    "primary_ip":v.primary_ip,"access_username":v.access_username,
                    "fingerprint":v.ssh_public_key_fingerprint,
                    "guest_ready_at":v.guest_ready_at.isoformat() if v.guest_ready_at else None,
                }
            if v.status=="failed":
                raise RuntimeError(f"VPS failed: {v.failure_category}: {v.failure_message}")
        time.sleep(3)
    raise RuntimeError(f"Timed out waiting for {wanted}; last={last}")

def queue(vps_id, action, wanted):
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.username=="humair-uddin"))
        v=db.get(VPSInstance,vps_id)
        queue_vps_action(db,vps=v,action=action,actor=actor)
    return wait_vps(vps_id,wanted)

def generate_key():
    td=tempfile.TemporaryDirectory(prefix="kc-secure-vps-")
    key=Path(td.name)/"id_ed25519"
    subprocess.run(
        ["ssh-keygen","-q","-t","ed25519","-N","","-C","khan-cloud-acceptance","-f",str(key)],
        check=True,
    )
    return td, key, key.with_suffix(".pub").read_text().strip()

def main():
    keydir,key_path,public_key=generate_key()
    try:
        with SessionLocal() as db:
            actor=db.scalar(select(User).where(User.username=="humair-uddin"))
            node=db.scalar(select(Node).where(Node.name==NODE_NAME))
            org=db.scalar(select(Organization).where(Organization.slug==ORG_SLUG))
            if actor is None or node is None or org is None: raise RuntimeError("Acceptance prerequisites missing")
            cap=sync_node_capacity(db,node)
            if not cap.scheduling_enabled: raise RuntimeError("R7425 not schedulable")
            before=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)

            existing=db.scalar(select(VPSInstance).where(VPSInstance.name==VPS_NAME).order_by(VPSInstance.created_at.desc()))
            if existing is not None and existing.status!="deleted":
                raise RuntimeError(f"Existing secure acceptance VPS is {existing.status}")

            vps=create_vps(
                db,
                payload=VPSCreate(
                    organization_id=org.id,name=VPS_NAME,image="ubuntu-24.04",
                    vcpu=2,memory_mb=1024,disk_gb=8,ssh_public_key=public_key,
                ),
                actor=actor,
            )
            vps_id=vps.id

        ready=wait_vps(vps_id,"running",240)
        if not ready["primary_ip"] or not ready["guest_ready_at"] or not ready["fingerprint"]:
            raise RuntimeError("Secure VPS did not return complete access/readiness data")

        stopped=queue(vps_id,"stop","stopped")
        started=queue(vps_id,"start","running")
        deleted=queue(vps_id,"delete","deleted")

        with SessionLocal() as db:
            node=db.scalar(select(Node).where(Node.name==NODE_NAME))
            cap=sync_node_capacity(db,node)
            after=(cap.cpu_allocated,cap.memory_allocated_bytes,cap.storage_allocated_bytes)
            if before != after: raise RuntimeError(f"Capacity leak: {before} != {after}")

        print(json.dumps({
            "status":"PASS",
            "vps_id":str(vps_id),
            "runtime_id":ready["runtime_id"],
            "primary_ip":ready["primary_ip"],
            "access_username":ready["access_username"],
            "ssh_public_key_fingerprint":ready["fingerprint"],
            "guest_ready_at":ready["guest_ready_at"],
            "create":"running_ssh_ready",
            "stop":stopped["status"],
            "start":started["status"],
            "delete":deleted["status"],
            "capacity_before":before,
            "capacity_after":after,
            "private_key_used_only_for_acceptance":str(key_path),
        },indent=2))
    finally:
        keydir.cleanup()

if __name__=="__main__": main()
