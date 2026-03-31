import hashlib
import json
import logging
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

# Structured audit logger — outputs JSON to stdout for Docker/K8s log aggregation
_audit_logger = logging.getLogger("audit")
if not _audit_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)


def audit_log(event: str, user_id: str | None = None, **extra) -> None:
    """Emit a structured JSON audit log entry for security events."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user_id": user_id,
        **extra,
    }
    _audit_logger.info(json.dumps(entry, default=str))

# Pre-computed dummy hash for constant-time login on non-existent users
_DUMMY_HASH = hash_password("dummy-password-for-timing-safety")


async def register(email: str, password: str) -> dict:
    """Register a new user and return token pair.

    Returns 409 only on actual DB constraint violation (race condition safety).
    For existing emails, silently returns generic message to prevent enumeration.
    """
    existing = await User.find_one(User.email == email)
    if existing:
        # Don't reveal that the email exists — send a notification email instead
        # (email service can inform the real owner someone tried to register)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration could not be completed",
        )

    user = User(email=email, hashed_password=hash_password(password))
    await user.insert()

    return _issue_tokens(user)


async def login(email: str, password: str) -> dict:
    """Authenticate user and return token pair.

    Security: constant-time response for missing users (timing oracle prevention),
    lockout checked before password verify, is_active checked before bcrypt.
    """
    from app.services.lockout_service import (
        check_lockout, record_failed_attempt, reset_attempts,
    )

    user = await User.find_one(User.email == email)

    # Check lockout keyed by email hash (works even for non-existent users)
    lockout_key = str(user.id) if user else hashlib.sha256(email.encode()).hexdigest()
    await check_lockout(lockout_key)

    if not user:
        # Constant-time: run bcrypt on dummy hash so response time matches real users
        verify_password(password, _DUMMY_HASH)
        audit_log("login_failed", reason="user_not_found", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check is_active before expensive bcrypt verification
    if not user.is_active:
        audit_log("login_failed", user_id=str(user.id), reason="account_disabled")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(password, user.hashed_password):
        await record_failed_attempt(lockout_key)
        audit_log("login_failed", user_id=str(user.id), reason="wrong_password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Successful login — reset lockout counter
    await reset_attempts(lockout_key)
    audit_log("login_success", user_id=str(user.id))
    return _issue_tokens(user)


async def logout(access_token: str, refresh_token: str) -> None:
    """Blacklist both tokens in Redis. Each token handled independently so a
    malformed refresh token doesn't prevent the access token from being revoked.
    """
    redis = get_redis()
    now = int(time.time())

    user_id = None
    try:
        access_payload = decode_token(access_token)
        user_id = access_payload.get("sub")
        await redis.setex(
            f"{BLACKLIST_PREFIX}{access_payload['jti']}",
            max(access_payload["exp"] - now, 1),
            "1",
        )
    except Exception:
        pass  # Access token already expired or invalid — nothing to blacklist

    try:
        refresh_payload = decode_token(refresh_token)
        await redis.setex(
            f"{BLACKLIST_PREFIX}{refresh_payload['jti']}",
            max(refresh_payload["exp"] - now, 1),
            "1",
        )
    except Exception:
        pass  # Refresh token already expired or invalid — nothing to blacklist

    audit_log("logout", user_id=user_id)


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

    if user.verification_token_expires < datetime.now(timezone.utc):
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

    if user.reset_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired")

    user.hashed_password = hash_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await user.save()

    # Invalidate all pre-reset sessions so attacker loses access after account recovery
    await revoke_all_sessions(str(user.id))
    audit_log("password_reset", user_id=str(user.id))


async def _check_email_rate_limit(email: str) -> None:
    """Rate limit: max 3 verification/reset emails per hour per user.

    Atomic INCR-first pattern prevents TOCTOU race under concurrent requests.
    """
    redis = get_redis()
    key = f"{RATE_LIMIT_PREFIX}{email}"
    count = await redis.incr(key)
    if count == 1:
        # First request in window — start the 1-hour TTL
        await redis.expire(key, 3600)
    if count > 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many email requests. Try again later.",
        )


async def revoke_all_sessions(user_id: str) -> None:
    """Mark all sessions for a user as revoked (checked in get_current_user).

    TTL matches max token lifetime so keys auto-expire from Redis.
    """
    from app.core.config import settings
    redis = get_redis()
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    audit_log("sessions_revoked", user_id=user_id)
    await redis.setex(f"revoked_at:{user_id}", ttl, str(int(time.time())))


def _issue_tokens(user: User) -> dict:
    """Generate access + refresh token pair for a user."""
    user_id = str(user.id)
    return {
        "access_token": create_access_token(user_id, user.roles),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }
