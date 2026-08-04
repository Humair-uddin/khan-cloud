from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.rbac_service import get_permission_codes


def require_permission(permission_code: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        permissions = get_permission_codes(user)
        if "*" not in permissions and permission_code not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_code}",
            )
        return user

    return dependency
