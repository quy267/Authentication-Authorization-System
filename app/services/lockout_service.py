from fastapi import HTTPException, status

from app.core.config import settings
from app.core.database import get_redis

LOCKOUT_PREFIX = "lockout:"


async def check_lockout(user_id: str) -> None:
    """Raise 423 if account is locked."""
    redis = get_redis()
    count = await redis.get(f"{LOCKOUT_PREFIX}{user_id}")
    if count and int(count) >= settings.LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account locked due to too many failed attempts. Try again later.",
        )


async def record_failed_attempt(user_id: str) -> None:
    """Increment failed attempt counter. TTL set only on first failure (fixed window)."""
    redis = get_redis()
    key = f"{LOCKOUT_PREFIX}{user_id}"
    new_count = await redis.incr(key)
    if new_count == 1:
        # First failure — start the lockout window clock
        await redis.expire(key, settings.LOCKOUT_DURATION_MINUTES * 60)


async def reset_attempts(user_id: str) -> None:
    """Clear failed attempt counter on successful login."""
    redis = get_redis()
    await redis.delete(f"{LOCKOUT_PREFIX}{user_id}")
