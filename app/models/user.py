from datetime import datetime, timezone

from beanie import Document, Indexed
from pydantic import EmailStr, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Document):
    """User document for authentication and authorization."""

    email: Indexed(EmailStr, unique=True)
    hashed_password: str
    is_active: bool = True
    is_verified: bool = False
    roles: list[str] = Field(default_factory=lambda: ["user"])

    # Email verification
    verification_token: str | None = None
    verification_token_expires: datetime | None = None

    # Password reset
    reset_token: str | None = None
    reset_token_expires: datetime | None = None

    # Account lockout
    failed_login_attempts: int = 0
    locked_until: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "users"
