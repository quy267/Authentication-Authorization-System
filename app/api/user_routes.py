from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.user import UserResponse, UserRolesUpdateRequest

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_role("admin")),
    skip: int = 0,
    limit: int = 20,
):
    users = await User.find_all().skip(skip).limit(limit).to_list()
    return [
        UserResponse(
            id=str(u.id), email=u.email, is_active=u.is_active,
            is_verified=u.is_verified, roles=u.roles,
        )
        for u in users
    ]


@router.put("/{user_id}/roles", response_model=UserResponse)
async def update_user_roles(
    user_id: str,
    body: UserRolesUpdateRequest,
    current_user: User = Depends(require_role("admin")),
):
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.roles = body.roles
    await user.save()
    return UserResponse(
        id=str(user.id), email=user.email, is_active=user.is_active,
        is_verified=user.is_verified, roles=user.roles,
    )


@router.post("/{user_id}/revoke-sessions", response_model=MessageResponse)
async def revoke_user_sessions(
    user_id: str,
    current_user: User = Depends(require_role("admin")),
):
    """Admin: revoke all sessions for a user via Redis blacklist prefix."""
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    from app.core.database import get_redis
    redis = get_redis()
    # Set a revocation timestamp — the auth dependency checks this
    await redis.set(f"revoked_at:{user_id}", str(int(__import__('time').time())))
    return {"message": f"All sessions revoked for user {user_id}"}
