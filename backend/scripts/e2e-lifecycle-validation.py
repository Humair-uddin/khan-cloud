#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.models.deployment_profile import DeploymentProfile
from app.models.installation_event import InstallationEvent
from app.models.node import Node
from app.models.organization import Organization, OrganizationMembership
from app.models.support_case import SupportCase
from app.models.user import User
from app.schemas.deployment_profile import DeploymentProfileCreate
from app.services.deployment_profile_service import create_profile, rotate_profile_code
from app.services.node_service import transition_node
from app.services.operations_dashboard_service import build_operations_dashboard
from app.services.organization_service import create_organization


ORG_NAME = "Khan Cloud Validation"
ORG_SLUG = "khan-cloud-validation"
PROFILE_NAME = "Khan Cloud E2E Validation"
NODE_NAME = "KC-E2E-VALIDATION"
MACHINE_ID = "khan-cloud-e2e-validation-node-v1"
BASE_URL = "http://127.0.0.1:8000"


def emit(event: str, **data: Any) -> None:
    print(json.dumps({"event": event, **data}, default=str))


def find_actor(db, username: str) -> User:
    actor = db.scalar(select(User).where(User.username == username))
    if actor is None:
        actor = db.scalar(select(User).where(User.email == username))
    if actor is None:
        raise RuntimeError(f"Control Plane user not found: {username}")
    if not actor.is_active:
        raise RuntimeError(f"Control Plane user is inactive: {username}")
    return actor


def ensure_organization(db, actor: User) -> Organization:
    org = db.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
    if org is None:
        org = create_organization(
            db,
            name=ORG_NAME,
            slug=ORG_SLUG,
            actor=actor,
        )
        emit("organization_created", organization_id=org.id, slug=org.slug)
    else:
        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org.id,
                OrganizationMembership.user_id == actor.id,
            )
        )
        if membership is None:
            db.add(
                OrganizationMembership(
                    organization_id=org.id,
                    user_id=actor.id,
                    role="owner",
                )
            )
            db.commit()
        emit("organization_reused", organization_id=org.id, slug=org.slug)
    return org


def ensure_profile(db, actor: User, org: Organization) -> tuple[DeploymentProfile, str]:
    profile = db.scalar(
        select(DeploymentProfile).where(
            DeploymentProfile.name == PROFILE_NAME,
            DeploymentProfile.organization_id == org.id,
        )
    )
    if profile is None:
        profile, code = create_profile(
            db,
            DeploymentProfileCreate(
                name=PROFILE_NAME,
                purpose="gpu_compute",
                ownership_type="organization",
                visibility="organization_only",
                control_plane_url=BASE_URL,
                allowed_services={"validation": True},
                resource_policy={"validation_only": True},
                max_uses=100,
                organization_id=org.id,
            ),
            actor.id,
        )
        emit("deployment_created", deployment_profile_id=profile.id)
        return profile, code

    profile.is_active = True
    db.commit()
    code = rotate_profile_code(db, profile, actor.id)
    emit("deployment_reused", deployment_profile_id=profile.id)
    return profile, code


def enroll_validation_node(code: str) -> dict[str, Any]:
    payload = {
        "name": NODE_NAME,
        "machine_id": MACHINE_ID,
        "hostname": "khan-cloud-e2e-validation",
        "operating_system": "Khan Cloud synthetic validation node",
        "kernel_version": "validation",
        "agent_version": "e2e-validation",
        "management_ip": "127.0.0.1",
        "production_ip": "",
        "inventory": {
            "cpu": {"model": "synthetic-validation", "logical_count": 1},
            "memory": {"total_bytes": 1073741824},
            "docker": {"available": False},
            "nvidia": {"available": False, "gpus": []},
        },
        "capabilities": {
            "linux": True,
            "ai_compute": False,
            "validation": True,
        },
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{BASE_URL}/api/v1/nodes/register",
            headers={"X-Deployment-Enrollment-Code": code},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def heartbeat(node_id: str, node_secret: str) -> dict[str, Any]:
    payload = {
        "hostname": "khan-cloud-e2e-validation",
        "operating_system": "Khan Cloud synthetic validation node",
        "kernel_version": "validation",
        "agent_version": "e2e-validation",
        "management_ip": "127.0.0.1",
        "production_ip": "",
        "inventory": {
            "cpu": {"model": "synthetic-validation", "logical_count": 1},
            "memory": {"total_bytes": 1073741824},
            "docker": {"available": False},
            "nvidia": {"available": False, "gpus": []},
        },
        "capabilities": {"linux": True, "validation": True},
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{BASE_URL}/api/v1/nodes/heartbeat",
            headers={
                "X-Node-ID": node_id,
                "X-Node-Secret": node_secret,
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def report_success(node_id: str, node_secret: str) -> dict[str, Any]:
    payload = {
        "transaction_id": "e2e-validation",
        "feature_pack_id": "FP-E2E-VALIDATION",
        "feature_pack_version": "1.0.0",
        "status": "success",
        "stage": "complete",
        "failure_category": "",
        "message": "Synthetic end-to-end lifecycle validation completed successfully.",
        "details": {
            "dry_run": False,
            "current_stage": "complete",
            "verified": True,
        },
        "reported_at": datetime.now(UTC).isoformat(),
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{BASE_URL}/api/v1/nodes/installation-events",
            headers={
                "X-Node-ID": node_id,
                "X-Node-Secret": node_secret,
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def validate_dashboard(db, actor: User, profile_id) -> dict[str, Any]:
    dashboard = build_operations_dashboard(db, actor, stale_after_seconds=300)
    deployment = next(
        (item for item in dashboard.deployments if item.profile_id == profile_id),
        None,
    )
    if deployment is None:
        raise RuntimeError("Validation deployment is missing from dashboard.")
    if deployment.total_nodes < 1:
        raise RuntimeError("Validation deployment has no visible node.")
    if deployment.online_nodes < 1:
        raise RuntimeError("Validation node is not online in dashboard.")
    if deployment.failed_nodes != 0:
        raise RuntimeError("Validation deployment unexpectedly reports failure.")

    return {
        "deployments_visible": dashboard.counts.deployments,
        "nodes_visible": dashboard.counts.nodes,
        "online_nodes": dashboard.counts.online_nodes,
        "validation_health": deployment.health,
        "validation_nodes": deployment.total_nodes,
        "validation_online": deployment.online_nodes,
        "validation_failed": deployment.failed_nodes,
    }


def cleanup(username: str) -> None:
    with SessionLocal() as db:
        actor = find_actor(db, username)
        org = db.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
        node = db.scalar(select(Node).where(Node.machine_id == MACHINE_ID))
        profile = db.scalar(
            select(DeploymentProfile).where(DeploymentProfile.name == PROFILE_NAME)
        )

        if node is not None:
            db.execute(delete(InstallationEvent).where(InstallationEvent.node_id == node.id))
            db.execute(delete(SupportCase).where(SupportCase.node_id == node.id))
            db.delete(node)
            db.flush()

        if profile is not None:
            db.execute(
                delete(SupportCase).where(
                    SupportCase.deployment_profile_id == profile.id
                )
            )
            db.delete(profile)
            db.flush()

        if org is not None:
            db.execute(
                delete(OrganizationMembership).where(
                    OrganizationMembership.organization_id == org.id
                )
            )
            db.execute(
                delete(SupportCase).where(SupportCase.organization_id == org.id)
            )
            db.delete(org)

        db.commit()
        emit("cleanup_complete", actor=actor.username)


def run(username: str) -> None:
    with SessionLocal() as db:
        actor = find_actor(db, username)
        org = ensure_organization(db, actor)
        profile, code = ensure_profile(db, actor, org)
        organization_id = org.id
        deployment_profile_id = profile.id

    registration = enroll_validation_node(code)
    emit(
        "node_enrolled",
        node_id=registration["node_id"],
        deployment_profile_id=registration["deployment_profile_id"],
        lifecycle_state=registration["lifecycle_state"],
    )

    with SessionLocal() as db:
        actor = find_actor(db, username)
        node = db.get(Node, registration["node_id"])
        if node is None:
            raise RuntimeError("Enrolled validation node disappeared.")
        if node.deployment_profile_id != deployment_profile_id:
            raise RuntimeError("Validation node was not bound to expected deployment.")
        if node.lifecycle_state == "pending_approval":
            node = transition_node(
                db,
                node=node,
                new_state="approved",
                actor_user_id=actor.id,
                reason="Automated E2E lifecycle validation.",
            )
        elif node.lifecycle_state != "approved":
            raise RuntimeError(
                f"Unexpected validation node lifecycle: {node.lifecycle_state}"
            )
        emit("node_approved", node_id=node.id, lifecycle_state=node.lifecycle_state)

    heart = heartbeat(registration["node_id"], registration["node_secret"])
    emit(
        "heartbeat_success",
        node_id=heart["id"],
        connectivity_state=heart["connectivity_state"],
    )

    event = report_success(registration["node_id"], registration["node_secret"])
    emit(
        "telemetry_success",
        event_id=event["id"],
        status=event["status"],
        stage=event["stage"],
    )

    with SessionLocal() as db:
        actor = find_actor(db, username)
        dashboard = validate_dashboard(db, actor, deployment_profile_id)

    emit(
        "e2e_success",
        organization_id=organization_id,
        deployment_profile_id=deployment_profile_id,
        node_id=registration["node_id"],
        dashboard=dashboard,
        dashboard_url="http://192.168.18.100:8000/ui/",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the Khan Cloud enrollment-to-dashboard lifecycle."
    )
    parser.add_argument("--user", default="humair-uddin")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    if args.cleanup:
        cleanup(args.user)
    else:
        run(args.user)


if __name__ == "__main__":
    main()
