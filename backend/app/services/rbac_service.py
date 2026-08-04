from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac import Permission, Role
from app.models.user import User


DEFAULT_PERMISSIONS: dict[str, str] = {
    "users.read": "View users.",
    "users.manage": "Create, update, suspend, and manage users.",
    "roles.read": "View roles and permissions.",
    "roles.manage": "Create roles and assign permissions.",
    "nodes.read": "View compute nodes and hardware inventory.",
    "nodes.manage": "Register, enable, disable, and maintain nodes.",
    "deployments.read": "View workload deployments.",
    "deployments.manage": "Create, start, stop, and terminate deployments.",
    "settings.read": "View platform settings.",
    "settings.manage": "Modify platform settings.",
}

DEFAULT_ROLES: dict[str, set[str]] = {
    "platform_admin": set(DEFAULT_PERMISSIONS),
    "operator": {
        "users.read",
        "roles.read",
        "nodes.read",
        "nodes.manage",
        "deployments.read",
        "deployments.manage",
        "settings.read",
    },
    "customer": {
        "nodes.read",
        "deployments.read",
        "deployments.manage",
    },
    "viewer": {
        "users.read",
        "roles.read",
        "nodes.read",
        "deployments.read",
        "settings.read",
    },
}


class RBACConflictError(ValueError):
    pass


class RBACNotFoundError(ValueError):
    pass


def seed_default_rbac(db: Session) -> None:
    permissions: dict[str, Permission] = {}

    for code, description in DEFAULT_PERMISSIONS.items():
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code, description=description)
            db.add(permission)
            db.flush()
        permissions[code] = permission

    for role_name, permission_codes in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name, description=f"Built-in {role_name} role.")
            db.add(role)
            db.flush()
        role.permissions = [permissions[code] for code in sorted(permission_codes)]

    db.commit()


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.name)).unique())


def create_role(
    db: Session,
    name: str,
    description: str,
    permission_codes: list[str],
) -> Role:
    if db.scalar(select(Role).where(Role.name == name)):
        raise RBACConflictError("Role already exists.")

    permissions = list(
        db.scalars(
            select(Permission).where(Permission.code.in_(permission_codes))
        ).unique()
    )
    found = {item.code for item in permissions}
    missing = sorted(set(permission_codes) - found)
    if missing:
        raise RBACNotFoundError(f"Unknown permissions: {', '.join(missing)}")

    role = Role(name=name, description=description, permissions=permissions)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def assign_role(db: Session, user: User, role_name: str) -> User:
    role = db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise RBACNotFoundError("Role not found.")

    if role not in user.roles:
        user.roles.append(role)
        db.commit()
        db.refresh(user)
    return user


def get_permission_codes(user: User) -> set[str]:
    if user.is_superuser:
        return {"*"}

    return {
        permission.code
        for role in user.roles
        for permission in role.permissions
    }


def get_role_names(user: User) -> list[str]:
    return sorted(role.name for role in user.roles)
