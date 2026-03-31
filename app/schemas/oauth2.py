from pydantic import BaseModel, field_validator


class OAuth2ClientCreateRequest(BaseModel):
    client_name: str
    redirect_uris: list[str] = []

    @field_validator("redirect_uris")
    @classmethod
    def validate_redirect_uris(cls, v: list[str]) -> list[str]:
        for uri in v:
            if not uri.startswith(("https://", "http://localhost", "http://127.0.0.1")):
                raise ValueError(f"redirect_uri must use HTTPS (except localhost): {uri}")
        return v
    allowed_scopes: list[str] = []
    grant_types: list[str] = ["authorization_code"]
    token_endpoint_auth_method: str = "client_secret_post"


class OAuth2ClientCreateResponse(BaseModel):
    """POST /oauth/clients response — exposes raw secret exactly once."""
    client_id: str
    client_secret: str | None = None
    client_name: str
    redirect_uris: list[str]
    allowed_scopes: list[str]
    grant_types: list[str]
    token_endpoint_auth_method: str


class OAuth2ClientListResponse(BaseModel):
    """GET /oauth/clients response — never exposes client_secret."""
    client_id: str
    client_name: str
    redirect_uris: list[str]
    allowed_scopes: list[str]
    grant_types: list[str]
    token_endpoint_auth_method: str


class OAuth2TokenRequest(BaseModel):
    grant_type: str
    code: str | None = None
    redirect_uri: str | None = None
    client_id: str
    client_secret: str | None = None
    code_verifier: str | None = None
    scope: str | None = None
    refresh_token: str | None = None


class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int  # Computed from _OAUTH2_ACCESS_TOKEN_TTL, not hardcoded
    scope: str = ""
    refresh_token: str | None = None


class OAuth2RevokeRequest(BaseModel):
    token: str
    client_id: str
    client_secret: str | None = None
    token_type_hint: str | None = None
