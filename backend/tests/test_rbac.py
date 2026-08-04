from types import SimpleNamespace

from app.services.rbac_service import get_permission_codes, get_role_names


def test_superuser_has_global_permission() -> None:
    user = SimpleNamespace(is_superuser=True, roles=[])
    assert get_permission_codes(user) == {"*"}


def test_user_permissions_are_combined() -> None:
    user = SimpleNamespace(
        is_superuser=False,
        roles=[
            SimpleNamespace(
                name="operator",
                permissions=[
                    SimpleNamespace(code="nodes.read"),
                    SimpleNamespace(code="nodes.manage"),
                ],
            ),
            SimpleNamespace(
                name="viewer",
                permissions=[SimpleNamespace(code="deployments.read")],
            ),
        ],
    )

    assert get_permission_codes(user) == {
        "nodes.read",
        "nodes.manage",
        "deployments.read",
    }
    assert get_role_names(user) == ["operator", "viewer"]
