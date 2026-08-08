#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.deployment_profile import DeploymentProfile
from app.models.node import Node
from app.models.user import User
from app.services.deployment_operations_service import (
    get_deployment_operations_summary,
)


PROFILE_NAME = "R7425 VPS Infrastructure"
NODE_NAME = "KC-R7425-VPS-01"


def find_actor(db, username: str) -> User:
    actor = db.scalar(select(User).where(User.username == username))
    if actor is None:
        actor = db.scalar(select(User).where(User.email == username))
    if actor is None:
        raise RuntimeError(f"Control Plane user not found: {username}")
    return actor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="humair-uddin")
    args = parser.parse_args()

    with SessionLocal() as db:
        find_actor(db, args.user)

        profile = db.scalar(
            select(DeploymentProfile).where(
                DeploymentProfile.name == PROFILE_NAME
            )
        )
        if profile is None:
            raise RuntimeError("R7425 VPS deployment profile not found.")

        node = db.scalar(
            select(Node).where(
                Node.name == NODE_NAME,
                Node.deployment_profile_id == profile.id,
            )
        )
        if node is None:
            raise RuntimeError("R7425 VPS node is not enrolled.")

        if node.last_seen_at is None:
            raise RuntimeError("R7425 has never sent a heartbeat.")

        seen = node.last_seen_at
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        heartbeat_age = (datetime.now(UTC) - seen).total_seconds()
        if heartbeat_age > 120:
            raise RuntimeError(
                f"R7425 heartbeat is stale: {heartbeat_age:.1f}s"
            )

        if node.intended_purpose != "vps_infrastructure":
            raise RuntimeError(
                f"Unexpected node purpose: {node.intended_purpose}"
            )

        inventory = node.inventory or {}
        memory = inventory.get("memory", {})
        docker = inventory.get("docker", {})
        nvidia = inventory.get("nvidia", {})

        if int(memory.get("total_bytes", 0) or 0) <= 0:
            raise RuntimeError("Real memory inventory was not collected.")
        if not docker.get("installed"):
            raise RuntimeError("Docker installation was not detected.")
        if not docker.get("active"):
            raise RuntimeError("Docker is not reported active.")
        if nvidia.get("available"):
            raise RuntimeError(
                "R7425 unexpectedly reports an available NVIDIA GPU."
            )
        if node.gpu_count != 0:
            raise RuntimeError(
                f"R7425 unexpectedly reports {node.gpu_count} GPUs."
            )

        summary = get_deployment_operations_summary(
            db,
            profile,
            stale_after_seconds=300,
        )

        result = {
            "status": "verified",
            "deployment_profile_id": str(profile.id),
            "node_id": str(node.id),
            "node_name": node.name,
            "purpose": node.intended_purpose,
            "connectivity": node.connectivity_state,
            "heartbeat_age_seconds": round(heartbeat_age, 1),
            "cpu_model": node.cpu_model,
            "logical_cpus": node.cpu_logical_count,
            "memory_total_bytes": node.memory_total_bytes,
            "docker_available": node.docker_available,
            "nvidia_available": node.nvidia_available,
            "gpu_count": node.gpu_count,
            "deployment_health": summary.health,
            "online_nodes": summary.online_nodes,
            "failed_nodes": summary.failed_nodes,
        }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
