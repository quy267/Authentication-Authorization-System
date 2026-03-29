import time

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.database import get_redis
from app.models.user import User
from app.services.role_service import validate_role_names


async def list_users(skip: int, limit: int) -> list[User]:
    """Return a paginated list of users."""
    return await User.find_all().skip(skip).limit(limit).to_list()


async def update_user_roles(user_id: str, roles: list[str]) -> User:
    """Assign roles to a user after validating all role names exist in DB."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid user ID")
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    await validate_role_names(roles)
    user.roles = roles
    await user.save()
    return user


async def revoke_user_sessions(user_id: str) -> None:
    """Revoke all active sessions for a user via Redis revocation timestamp with TTL."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid user ID")
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    redis = get_redis()
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400  # Key expires when longest token expires
    await redis.setex(f"revoked_at:{user_id}", ttl, str(int(time.time())))
