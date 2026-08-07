from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationMembership
from app.models.user import User
from app.services.audit_service import record_audit_event
from app.services.rbac_service import get_role_names


class OrganizationError(ValueError):
    pass


def create_organization(db: Session, *, name: str, slug: str, actor: User) -> Organization:
    existing = db.scalar(select(Organization).where(Organization.slug == slug))
    if existing is not None:
        raise OrganizationError("Organization slug already exists.")
    org = Organization(name=name, slug=slug, created_by_user_id=actor.id, is_active=True)
    db.add(org); db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=actor.id, role="owner"))
    record_audit_event(db, actor_user_id=actor.id, action="organization.created", resource_type="organization", resource_id=str(org.id))
    db.commit(); db.refresh(org)
    return org


def add_member(db: Session, *, organization_id: UUID, user_id: UUID, role: str, actor: User) -> OrganizationMembership:
    if db.get(Organization, organization_id) is None:
        raise OrganizationError("Organization not found.")
    existing = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_id == user_id))
    if existing is not None:
        existing.role = role; membership = existing
    else:
        membership = OrganizationMembership(organization_id=organization_id, user_id=user_id, role=role); db.add(membership)
    record_audit_event(db, actor_user_id=actor.id, action="organization.member_updated", resource_type="organization", resource_id=str(organization_id), details={"user_id": str(user_id), "role": role})
    db.commit(); db.refresh(membership)
    return membership


def user_can_access_organization(db: Session, user: User, organization_id: UUID) -> bool:
    if user.is_superuser:
        return True
    staff_roles = {"platform_owner", "platform_admin", "operator", "support_engineer"}
    if staff_roles.intersection(get_role_names(user)):
        return True
    return db.scalar(select(OrganizationMembership.id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_id == user.id)) is not None


def visible_organizations(db: Session, user: User) -> list[Organization]:
    if user.is_superuser or {"platform_owner", "platform_admin", "operator", "support_engineer"}.intersection(get_role_names(user)):
        return list(db.scalars(select(Organization).order_by(Organization.name)).unique())
    return list(db.scalars(select(Organization).join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id).where(OrganizationMembership.user_id == user.id).order_by(Organization.name)).unique())


def user_can_access_deployment_profile(db: Session, user: User, profile) -> bool:
    if profile.organization_id is not None:
        return user_can_access_organization(db, user, profile.organization_id)
    if user.is_superuser:
        return True
    return bool(
        {"platform_owner", "platform_admin", "operator", "support_engineer"}
        .intersection(get_role_names(user))
    )
