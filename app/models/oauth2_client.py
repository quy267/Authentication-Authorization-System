from datetime import datetime

from beanie import Document, Indexed
from pydantic import Field

from app.models.user import _utcnow


class OAuth2Client(Document):
    """OAuth2 client registration."""

    client_id: Indexed(str, unique=True)
    client_secret: str | None = None  # None for public clients
    client_name: str
    redirect_uris: list[str] = []
    allowed_scopes: list[str] = []
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code"]
    )
    token_endpoint_auth_method: str = "client_secret_post"
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "oauth2_clients"
