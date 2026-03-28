from pydantic import BaseModel


class OAuth2ClientCreateRequest(BaseModel):
    client_name: str
    redirect_uris: list[str] = []
    allowed_scopes: list[str] = []
    grant_types: list[str] = ["authorization_code"]
    token_endpoint_auth_method: str = "client_secret_post"


class OAuth2ClientResponse(BaseModel):
    client_id: str
    client_secret: str | None = None
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
    expires_in: int = 3600
    scope: str = ""
    refresh_token: str | None = None


class OAuth2RevokeRequest(BaseModel):
    token: str
    token_type_hint: str | None = None
