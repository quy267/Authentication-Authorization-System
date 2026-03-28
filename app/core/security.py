import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(
        plain.encode("utf-8"), hashed.encode("utf-8")
    )


def create_access_token(
    user_id: str,
    roles: list[str],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token with user_id, roles, jti."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": user_id,
        "roles": roles,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token with user_id and jti."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises on invalid/expired."""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
