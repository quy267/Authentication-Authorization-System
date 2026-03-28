import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status

from app.core.security import hash_password, verify_password
from app.models.oauth2_client import OAuth2Client
from app.models.oauth2_token import OAuth2AuthorizationCode, OAuth2Token


async def create_client(
    client_name: str,
    redirect_uris: list[str],
    allowed_scopes: list[str],
    grant_types: list[str],
    token_endpoint_auth_method: str,
) -> tuple[OAuth2Client, str | None]:
    """Register a new OAuth2 client. Returns (client, raw_secret)."""
    client_id = secrets.token_urlsafe(16)
    raw_secret = None
    hashed_secret = None
    if token_endpoint_auth_method != "none":
        raw_secret = secrets.token_urlsafe(32)
        hashed_secret = hash_password(raw_secret)

    client = OAuth2Client(
        client_id=client_id,
        client_secret=hashed_secret,
        client_name=client_name,
        redirect_uris=redirect_uris,
        allowed_scopes=allowed_scopes,
        grant_types=grant_types,
        token_endpoint_auth_method=token_endpoint_auth_method,
    )
    await client.insert()
    return client, raw_secret


async def authorize(
    client_id: str,
    redirect_uri: str,
    scope: str,
    user_id: str,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> str:
    """Issue an authorization code for the auth code flow."""
    client = await OAuth2Client.find_one(OAuth2Client.client_id == client_id)
    if not client or not client.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client_id")

    if redirect_uri not in client.redirect_uris:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid redirect_uri")

    if "authorization_code" not in client.grant_types:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Grant type not allowed")

    # PKCE mandatory for public clients
    if client.token_endpoint_auth_method == "none" and not code_challenge:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "PKCE required for public clients",
        )

    # Validate requested scopes
    requested = set(scope.split()) if scope else set()
    if not requested.issubset(set(client.allowed_scopes)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid scope")

    code = secrets.token_urlsafe(32)
    auth_code = OAuth2AuthorizationCode(
        code=code,
        client_id=client_id,
        user_id=user_id,
        redirect_uri=redirect_uri,
        scope=scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    await auth_code.insert()
    return code


async def exchange_code(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str | None = None,
    code_verifier: str | None = None,
) -> dict:
    """Exchange authorization code for tokens."""
    auth_code = await OAuth2AuthorizationCode.find_one(
        OAuth2AuthorizationCode.code == code
    )
    if not auth_code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code")

    if auth_code.used:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code already used")

    if auth_code.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code expired")

    if auth_code.client_id != client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client mismatch")

    if auth_code.redirect_uri != redirect_uri:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Redirect URI mismatch")

    # Validate client
    client = await OAuth2Client.find_one(OAuth2Client.client_id == client_id)
    if not client:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client")

    # Verify client credentials for confidential clients
    if client.token_endpoint_auth_method != "none":
        if not verify_password(client_secret, client.client_secret):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client secret")

    # PKCE verification
    if auth_code.code_challenge:
        if not code_verifier:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code verifier required")
        if not _verify_pkce(
            code_verifier, auth_code.code_challenge, auth_code.code_challenge_method
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code verifier")

    # Mark code as used
    auth_code.used = True
    await auth_code.save()

    return await _issue_oauth2_tokens(client_id, auth_code.user_id, auth_code.scope)


async def client_credentials_grant(
    client_id: str,
    client_secret: str,
    scope: str = "",
) -> dict:
    """Issue tokens via client credentials grant."""
    client = await OAuth2Client.find_one(OAuth2Client.client_id == client_id)
    if not client or not client.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client")

    if "client_credentials" not in client.grant_types:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Grant type not allowed")

    if not verify_password(client_secret, client.client_secret):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client secret")

    # Validate scopes
    requested = set(scope.split()) if scope else set()
    if not requested.issubset(set(client.allowed_scopes)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid scope")

    return await _issue_oauth2_tokens(client_id, None, scope, include_refresh=False)


async def refresh_oauth2_token(
    refresh_token: str,
    client_id: str,
) -> dict:
    """Refresh an OAuth2 token."""
    token_record = await OAuth2Token.find_one(
        OAuth2Token.refresh_token == refresh_token
    )
    if not token_record or token_record.revoked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid refresh token")

    if token_record.client_id != client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client mismatch")

    # Revoke old token
    token_record.revoked = True
    await token_record.save()

    return await _issue_oauth2_tokens(
        client_id, token_record.user_id, token_record.scope
    )


async def revoke_token(token: str) -> None:
    """Revoke an access or refresh token (RFC 7009 — always 200)."""
    # Try access token
    record = await OAuth2Token.find_one(OAuth2Token.access_token == token)
    if record:
        record.revoked = True
        await record.save()
        return

    # Try refresh token
    record = await OAuth2Token.find_one(OAuth2Token.refresh_token == token)
    if record:
        record.revoked = True
        await record.save()


async def _issue_oauth2_tokens(
    client_id: str,
    user_id: str | None,
    scope: str,
    include_refresh: bool = True,
) -> dict:
    """Create and persist OAuth2 token record."""
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32) if include_refresh else None

    token = OAuth2Token(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        user_id=user_id,
        scope=scope,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    await token.insert()

    result = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": scope,
    }
    if refresh_token:
        result["refresh_token"] = refresh_token
    return result


def _verify_pkce(
    code_verifier: str,
    code_challenge: str,
    method: str | None,
) -> bool:
    """Verify PKCE code_verifier against stored code_challenge."""
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        import base64
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return computed == code_challenge
    # plain method
    return code_verifier == code_challenge
