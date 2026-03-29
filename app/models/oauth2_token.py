from datetime import datetime

from beanie import Document, Indexed
from pymongo import ASCENDING, IndexModel


class OAuth2AuthorizationCode(Document):
    """Temporary authorization code for OAuth2 auth code flow."""

    code: Indexed(str, unique=True)
    client_id: str
    user_id: str
    redirect_uri: str
    scope: str = ""
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    expires_at: datetime  # Required — set explicitly at creation (no default to avoid instant expiry)
    used: bool = False

    class Settings:
        name = "oauth2_authorization_codes"
        indexes = [
            # TTL: MongoDB auto-deletes expired codes (expireAfterSeconds=0 means
            # delete at the datetime stored in expires_at)
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]


class OAuth2Token(Document):
    """OAuth2 access/refresh token record."""

    access_token: Indexed(str, unique=True)
    refresh_token: str | None = None  # None for client_credentials grant
    client_id: str
    user_id: str | None = None  # None for client_credentials
    scope: str = ""
    token_type: str = "Bearer"
    expires_at: datetime  # Required — set explicitly at creation (no default to avoid instant expiry)
    revoked: bool = False

    class Settings:
        name = "oauth2_tokens"
        indexes = [
            # Sparse unique index: allows multiple None values (client_credentials tokens)
            IndexModel([("refresh_token", ASCENDING)], unique=True, sparse=True),
            # TTL: MongoDB auto-deletes expired tokens
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]
