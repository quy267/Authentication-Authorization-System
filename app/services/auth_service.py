import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core.database import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User

# Redis key prefixes
BLACKLIST_PREFIX = "bl:"
RATE_LIMIT_PREFIX = "rl:email:"


async def register(email: str, password: str) -> dict:
    """Register a new user and return token pair."""
    existing = await User.find_one(User.email == email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(email=email, hashed_password=hash_password(password))
    await user.insert()

    return _issue_tokens(user)


async def login(email: str, password: str) -> dict:
    """Authenticate user and return token pair."""
    from app.services.lockout_service import (
        check_lockout, record_failed_attempt, reset_attempts,
    )

    user = await User.find_one(User.email == email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check lockout before password verification
    await check_lockout(str(user.id))

    if not verify_password(password, user.hashed_password):
        await record_failed_attempt(str(user.id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    # Successful login — reset lockout counter
    await reset_attempts(str(user.id))
    return _issue_tokens(user)


async def logout(access_token: str, refresh_token: str) -> None:
    """Blacklist both tokens in Redis."""
    redis = get_redis()
    now = int(time.time())

    access_payload = decode_token(access_token)
    await redis.setex(
        f"{BLACKLIST_PREFIX}{access_payload['jti']}",
        max(access_payload["exp"] - now, 1),
        "1",
    )

    refresh_payload = decode_token(refresh_token)
    await redis.setex(
        f"{BLACKLIST_PREFIX}{refresh_payload['jti']}",
        max(refresh_payload["exp"] - now, 1),
        "1",
    )


async def refresh(refresh_token_str: str) -> dict:
    """Validate refresh token, blacklist it, issue new pair."""
    try:
        payload = decode_token(refresh_token_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    # Check blacklist
    redis = get_redis()
    if await redis.get(f"{BLACKLIST_PREFIX}{payload['jti']}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Blacklist old refresh token (TTL = remaining lifetime, not total)
    await redis.setex(
        f"{BLACKLIST_PREFIX}{payload['jti']}",
        max(payload["exp"] - int(time.time()), 1),
        "1",
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

    return _issue_tokens(user)


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token jti is in the Redis blacklist."""
    redis = get_redis()
    return await redis.get(f"{BLACKLIST_PREFIX}{jti}") is not None


async def send_verification(user: User) -> None:
    """Generate verification token and send email."""
    await _check_email_rate_limit(user.email)

    token = secrets.token_urlsafe(32)
    user.verification_token = token
    user.verification_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await user.save()

    from app.services.email_service import send_verification_email
    await send_verification_email(user.email, token)


async def verify_email(token: str) -> None:
    """Verify email with token."""
    user = await User.find_one(User.verification_token == token)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid token")

    if user.is_verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already verified")

    if user.verification_token_expires < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired")

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    await user.save()


async def request_password_reset(email: str) -> None:
    """Generate reset token and send email. Always 200 to prevent enumeration."""
    user = await User.find_one(User.email == email)
    if not user:
        return  # Silent — no enumeration

    await _check_email_rate_limit(email)

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    await user.save()

    from app.services.email_service import send_reset_email
    await send_reset_email(email, token)


async def reset_password(token: str, new_password: str) -> None:
    """Reset password using token."""
    user = await User.find_one(User.reset_token == token)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid token")

    if user.reset_token_expires < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired")

    user.hashed_password = hash_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await user.save()

    # Invalidate all pre-reset sessions so attacker loses access after account recovery
    await _revoke_all_sessions(str(user.id))


async def _check_email_rate_limit(email: str) -> None:
    """Rate limit: max 3 verification/reset emails per hour per user."""
    redis = get_redis()
    key = f"{RATE_LIMIT_PREFIX}{email}"
    count = await redis.get(key)
    if count and int(count) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many email requests. Try again later.",
        )
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 3600)  # 1 hour TTL
    await pipe.execute()


async def _revoke_all_sessions(user_id: str) -> None:
    """Mark all sessions for a user as revoked (checked in get_current_user)."""
    redis = get_redis()
    await redis.set(f"revoked_at:{user_id}", str(int(time.time())))


def _issue_tokens(user: User) -> dict:
    """Generate access + refresh token pair for a user."""
    user_id = str(user.id)
    return {
        "access_token": create_access_token(user_id, user.roles),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }
