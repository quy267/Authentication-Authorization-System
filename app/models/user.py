from datetime import datetime, timezone

from beanie import Document, Indexed, Replace, before_event
from pydantic import EmailStr, Field
from pymongo import ASCENDING, IndexModel


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

    # Timestamps (lockout tracking is handled in Redis, not DB)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @before_event(Replace)
    def update_timestamp(self):
        self.updated_at = _utcnow()

    class Settings:
        name = "users"
        indexes = [
            # Sparse indexes: only index non-null token values (most users have None)
            IndexModel([("verification_token", ASCENDING)], sparse=True),
            IndexModel([("reset_token", ASCENDING)], sparse=True),
        ]
