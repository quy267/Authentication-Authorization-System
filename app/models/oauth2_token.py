from datetime import datetime

from beanie import Document, Indexed
from pydantic import Field

from app.models.user import _utcnow


class OAuth2AuthorizationCode(Document):
    """Temporary authorization code for OAuth2 auth code flow."""

    code: Indexed(str, unique=True)
    client_id: str
    user_id: str
    redirect_uri: str
    scope: str = ""
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    expires_at: datetime = Field(default_factory=_utcnow)
    used: bool = False

    class Settings:
        name = "oauth2_authorization_codes"


class OAuth2Token(Document):
    """OAuth2 access/refresh token record."""

    access_token: Indexed(str, unique=True)
    refresh_token: str | None = None
    client_id: str
    user_id: str | None = None  # None for client_credentials
    scope: str = ""
    token_type: str = "Bearer"
    expires_at: datetime = Field(default_factory=_utcnow)
    revoked: bool = False

    class Settings:
        name = "oauth2_tokens"
