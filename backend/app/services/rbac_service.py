from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.rbac import Permission, Role
from app.models.user import User

DEFAULT_PERMISSIONS: dict[str,str] = {
"users.read":"View users.","users.manage":"Manage users.",
"roles.read":"View roles and permissions.","roles.manage":"Manage roles.",
"nodes.read":"View nodes.","nodes.register":"Register nodes.",
"nodes.approve":"Approve or reject nodes.","nodes.disable":"Disable or enable nodes.",
"nodes.maintenance":"Manage node maintenance.","nodes.retire":"Retire nodes.",
"nodes.inventory.read":"View node inventory and capabilities.",
"nodes.credentials.rotate":"Rotate node credentials.","audit.read":"View audit records.",
"deployment_profiles.read":"View deployment profiles.",
"deployment_profiles.manage":"Create and manage deployment profiles.",
"organizations.read":"View organizations.","organizations.manage":"Manage organizations and memberships.",
"support.read":"View support cases.","support.manage":"Create and manage support cases.",
"deployments.read":"View deployments.","deployments.manage":"Manage deployments.",
"node_installers.manage":"Generate scoped node installers.",
"compute.hosts.read":"View compute host capacity.",
"vps.read":"View VPS instances.","vps.manage":"Create and manage VPS instances.",
"settings.read":"View settings.","settings.manage":"Modify settings.",
}
DEFAULT_ROLES: dict[str,set[str]] = {
"platform_owner": set(DEFAULT_PERMISSIONS),
"platform_admin": set(DEFAULT_PERMISSIONS),
"operator":{"users.read","roles.read","nodes.read","nodes.approve","nodes.disable",
"nodes.maintenance","nodes.inventory.read","audit.read","deployments.read",
"deployments.manage","node_installers.manage","compute.hosts.read","vps.read","vps.manage","organizations.read","support.read","support.manage","settings.read"},
"security_officer":{"users.read","roles.read","nodes.read","nodes.disable",
"nodes.credentials.rotate","nodes.inventory.read","audit.read","settings.read"},
"marketplace_manager":{"nodes.read","nodes.approve","nodes.inventory.read","audit.read","deployments.read","node_installers.manage"},
"support_engineer":{"users.read","nodes.read","nodes.inventory.read","audit.read","deployments.read","organizations.read","support.read","support.manage"},
"customer":{"nodes.read","deployments.read","deployments.manage","node_installers.manage","vps.read","vps.manage","organizations.read","support.read","support.manage"},
"viewer":{"users.read","roles.read","nodes.read","nodes.inventory.read","audit.read","deployments.read","settings.read"},
}
class RBACConflictError(ValueError): pass
class RBACNotFoundError(ValueError): pass

def seed_default_rbac(db: Session) -> None:
    permissions={}
    for code,description in DEFAULT_PERMISSIONS.items():
        p=db.scalar(select(Permission).where(Permission.code==code))
        if p is None:
            p=Permission(code=code,description=description); db.add(p); db.flush()
        permissions[code]=p
    for role_name,codes in DEFAULT_ROLES.items():
        r=db.scalar(select(Role).where(Role.name==role_name))
        if r is None:
            r=Role(name=role_name,description=f"Built-in {role_name} role."); db.add(r); db.flush()
        r.permissions=[permissions[c] for c in sorted(codes)]
    db.commit()

def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.name)).unique())

def create_role(db: Session,name: str,description: str,permission_codes: list[str]) -> Role:
    if db.scalar(select(Role).where(Role.name==name)): raise RBACConflictError("Role already exists.")
    permissions=list(db.scalars(select(Permission).where(Permission.code.in_(permission_codes))).unique())
    found={p.code for p in permissions}; missing=sorted(set(permission_codes)-found)
    if missing: raise RBACNotFoundError(f"Unknown permissions: {', '.join(missing)}")
    r=Role(name=name,description=description,permissions=permissions)
    db.add(r); db.commit(); db.refresh(r); return r

def assign_role(db: Session,user: User,role_name: str) -> User:
    r=db.scalar(select(Role).where(Role.name==role_name))
    if r is None: raise RBACNotFoundError("Role not found.")
    if r not in user.roles:
        user.roles.append(r); db.commit(); db.refresh(user)
    return user

def get_permission_codes(user: User) -> set[str]:
    if user.is_superuser: return {"*"}
    return {p.code for r in user.roles for p in r.permissions}

def get_role_names(user: User) -> list[str]:
    return sorted(r.name for r in user.roles)
