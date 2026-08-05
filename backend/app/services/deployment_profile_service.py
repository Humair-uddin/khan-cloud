import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment_profile import DeploymentProfile
from app.schemas.deployment_profile import DeploymentProfileCreate
from app.services.audit_service import record_audit_event


class DeploymentProfileError(ValueError):
    pass


def hash_enrollment_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_enrollment_code() -> str:
    return "kcdep_" + secrets.token_urlsafe(32)


def _validate_profile_policy(payload: DeploymentProfileCreate) -> None:
    if payload.purpose == "vps_infrastructure":
        if payload.ownership_type not in {"khan_cloud", "trusted_partner"}:
            raise DeploymentProfileError(
                "VPS infrastructure is restricted to Khan Cloud or trusted partners."
            )
        if payload.visibility == "public_marketplace":
            raise DeploymentProfileError(
                "VPS infrastructure profiles cannot be public provider listings."
            )

    if payload.purpose == "internal_lab" and payload.visibility != "internal_only":
        raise DeploymentProfileError(
            "Internal/lab profiles must use internal_only visibility."
        )

    if payload.purpose == "gaming_host":
        services = payload.allowed_services
        if services.get("vps") or services.get("enterprise_vm"):
            raise DeploymentProfileError(
                "Gaming host profiles cannot enable VPS or enterprise VM services."
            )


def create_profile(
    db: Session,
    payload: DeploymentProfileCreate,
    actor_user_id: UUID,
) -> tuple[DeploymentProfile, str]:
    _validate_profile_policy(payload)
    code = create_enrollment_code()

    profile = DeploymentProfile(
        name=payload.name,
        purpose=payload.purpose,
        ownership_type=payload.ownership_type,
        visibility=payload.visibility,
        control_plane_url=str(payload.control_plane_url).rstrip("/"),
        allowed_services=payload.allowed_services,
        resource_policy=payload.resource_policy,
        enrollment_code_hash=hash_enrollment_code(code),
        enrollment_code_prefix=code[:12],
        expires_at=payload.expires_at,
        max_uses=payload.max_uses,
        uses_count=0,
        created_by_user_id=actor_user_id,
        is_active=True,
    )
    db.add(profile)
    db.flush()

    record_audit_event(
        db,
        actor_user_id=actor_user_id,
        action="deployment_profile.created",
        resource_type="deployment_profile",
        resource_id=str(profile.id),
        details={
            "purpose": profile.purpose,
            "ownership_type": profile.ownership_type,
            "visibility": profile.visibility,
        },
    )
    db.commit()
    db.refresh(profile)
    return profile, code


def resolve_profile(db: Session, enrollment_code: str) -> DeploymentProfile:
    code_hash = hash_enrollment_code(enrollment_code)
    profile = db.scalar(
        select(DeploymentProfile).where(
            DeploymentProfile.enrollment_code_hash == code_hash
        )
    )
    if profile is None:
        raise DeploymentProfileError("Invalid deployment enrollment code.")
    if not profile.is_active:
        raise DeploymentProfileError("Deployment profile is disabled.")
    if profile.expires_at is not None and profile.expires_at <= datetime.now(UTC):
        raise DeploymentProfileError("Deployment enrollment code has expired.")
    if profile.uses_count >= profile.max_uses:
        raise DeploymentProfileError("Deployment enrollment code has no remaining uses.")
    return profile


def consume_profile_code(db: Session, profile: DeploymentProfile) -> None:
    profile.uses_count += 1
    db.commit()


def rotate_profile_code(
    db: Session,
    profile: DeploymentProfile,
    actor_user_id: UUID,
) -> str:
    code = create_enrollment_code()
    profile.enrollment_code_hash = hash_enrollment_code(code)
    profile.enrollment_code_prefix = code[:12]
    profile.uses_count = 0

    record_audit_event(
        db,
        actor_user_id=actor_user_id,
        action="deployment_profile.code_rotated",
        resource_type="deployment_profile",
        resource_id=str(profile.id),
    )
    db.commit()
    return code
