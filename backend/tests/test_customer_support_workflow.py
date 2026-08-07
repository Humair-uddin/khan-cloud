from types import SimpleNamespace
from uuid import uuid4

from app.services.organization_service import user_can_access_deployment_profile
from app.services.support_service import SupportCaseError


class FakeDB:
    def __init__(self, membership=False):
        self.membership = membership

    def scalar(self, statement):
        return uuid4() if self.membership else None


def user(*roles, superuser=False):
    return SimpleNamespace(
        id=uuid4(),
        is_superuser=superuser,
        roles=[SimpleNamespace(name=r, permissions=[]) for r in roles],
    )


def profile(org_id=None):
    return SimpleNamespace(organization_id=org_id)


def test_superuser_can_access_any_deployment():
    assert user_can_access_deployment_profile(
        FakeDB(), user(superuser=True), profile(uuid4())
    )


def test_support_engineer_can_access_any_organization_deployment():
    assert user_can_access_deployment_profile(
        FakeDB(), user("support_engineer"), profile(uuid4())
    )


def test_customer_member_can_access_own_organization_deployment():
    assert user_can_access_deployment_profile(
        FakeDB(membership=True), user("customer"), profile(uuid4())
    )


def test_customer_cannot_access_other_organization_deployment():
    assert not user_can_access_deployment_profile(
        FakeDB(membership=False), user("customer"), profile(uuid4())
    )


def test_customer_cannot_access_unowned_internal_deployment():
    assert not user_can_access_deployment_profile(
        FakeDB(), user("customer"), profile(None)
    )


def test_operator_can_access_unowned_internal_deployment():
    assert user_can_access_deployment_profile(
        FakeDB(), user("operator"), profile(None)
    )


def test_support_case_error_is_value_error():
    assert issubclass(SupportCaseError, ValueError)
