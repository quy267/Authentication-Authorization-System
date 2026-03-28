from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_token
from app.models.role import Role
from app.models.user import User
from app.services.auth_service import is_token_blacklisted

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> User:
    """Extract and validate JWT from Authorization header, return User."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    if await is_token_blacklisted(payload["jti"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    user = await User.get(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    return user


def require_role(role_name: str) -> Callable:
    """Dependency factory: require the current user to have a specific role."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        if role_name not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_name}' required",
            )
        return user
    return _check


def require_permission(permission: str) -> Callable:
    """Dependency factory: require the current user to have a specific permission."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        # Load all roles the user has and collect permissions
        user_permissions: set[str] = set()
        for role_name in user.roles:
            role = await Role.find_one(Role.name == role_name)
            if role:
                user_permissions.update(role.permissions)

        if permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return user
    return _check
