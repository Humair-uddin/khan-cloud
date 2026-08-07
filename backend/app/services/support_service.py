from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment_profile import DeploymentProfile
from app.models.node import Node
from app.models.support_case import SupportCase
from app.models.user import User
from app.schemas.support_case import SupportCaseCreate, SupportCaseUpdate
from app.services.audit_service import record_audit_event
from app.services.organization_service import user_can_access_organization


class SupportCaseError(ValueError):
    pass


def create_support_case(db: Session, payload: SupportCaseCreate, actor: User) -> SupportCase:
    if not user_can_access_organization(db, actor, payload.organization_id):
        raise SupportCaseError("Organization access denied.")
    profile = db.get(DeploymentProfile, payload.deployment_profile_id)
    if profile is None or profile.organization_id != payload.organization_id:
        raise SupportCaseError("Deployment does not belong to organization.")
    if payload.node_id is not None:
        node = db.get(Node, payload.node_id)
        if node is None or node.deployment_profile_id != profile.id:
            raise SupportCaseError("Node does not belong to deployment.")
    case = SupportCase(**payload.model_dump(), status="open", created_by_user_id=actor.id)
    db.add(case); db.flush()
    record_audit_event(db, actor_user_id=actor.id, action="support_case.created", resource_type="support_case", resource_id=str(case.id), details={"priority": case.priority, "category": case.category})
    db.commit(); db.refresh(case); return case


def update_support_case(db: Session, case: SupportCase, payload: SupportCaseUpdate, actor: User) -> SupportCase:
    if not user_can_access_organization(db, actor, case.organization_id):
        raise SupportCaseError("Organization access denied.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(case, key, value)
    if payload.status == "resolved":
        case.resolved_at = datetime.now(UTC)
    elif payload.status is not None:
        case.resolved_at = None
    record_audit_event(db, actor_user_id=actor.id, action="support_case.updated", resource_type="support_case", resource_id=str(case.id), details={"status": case.status, "priority": case.priority})
    db.commit(); db.refresh(case); return case


def visible_support_cases(db: Session, user: User) -> list[SupportCase]:
    cases = list(db.scalars(select(SupportCase).order_by(SupportCase.created_at.desc())).unique())
    return [case for case in cases if user_can_access_organization(db, user, case.organization_id)]
