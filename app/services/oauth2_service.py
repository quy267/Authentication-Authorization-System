import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core.security import hash_password, verify_password
from app.models.oauth2_client import OAuth2Client
from app.models.oauth2_token import OAuth2AuthorizationCode, OAuth2Token

# RFC 6749 timing constants — change here to update both storage and response
_AUTH_CODE_TTL = timedelta(minutes=5)
_OAUTH2_ACCESS_TOKEN_TTL = timedelta(hours=1)


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

    # Only S256 PKCE method is supported (plain method exposes verifier in URL)
    if code_challenge_method and code_challenge_method != "S256":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only S256 PKCE method is supported",
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
        expires_at=datetime.now(timezone.utc) + _AUTH_CODE_TTL,
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
        # RFC 6749 §4.1.2: revoke all tokens issued from this code on reuse
        await OAuth2Token.find(
            OAuth2Token.client_id == auth_code.client_id,
            OAuth2Token.user_id == auth_code.user_id,
        ).update({"$set": {"revoked": True}})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code already used")

    if auth_code.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code expired")

    if auth_code.client_id != client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client mismatch")

    if auth_code.redirect_uri != redirect_uri:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Redirect URI mismatch")

    # Validate client
    client = await OAuth2Client.find_one(OAuth2Client.client_id == client_id)
    if not client:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client")

    # Verify client credentials for confidential clients (guard None before bcrypt)
    if client.token_endpoint_auth_method != "none":
        if not client_secret:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client secret required")
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

    # Atomic mark-as-used: prevents double-spend race via motor findOneAndUpdate
    collection = OAuth2AuthorizationCode.get_motor_collection()
    matched = await collection.find_one_and_update(
        {"_id": auth_code.id, "used": False},
        {"$set": {"used": True}},
    )
    if matched is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code already used")

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

    # Public clients must not use client_credentials grant (no secret to verify)
    if not client.client_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Public clients cannot use client_credentials grant")

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
    client_secret: str | None = None,
) -> dict:
    """Refresh an OAuth2 token (atomic revocation to prevent TOCTOU race)."""
    token_record = await OAuth2Token.find_one(
        OAuth2Token.refresh_token == refresh_token
    )
    if not token_record or token_record.revoked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid refresh token")

    if token_record.client_id != client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client mismatch")

    # Verify client secret for confidential clients (guard None before bcrypt)
    client = await OAuth2Client.find_one(OAuth2Client.client_id == client_id)
    if not client:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client")

    if client.token_endpoint_auth_method != "none":
        if not client_secret:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client secret required")
        if not client.client_secret or not verify_password(client_secret, client.client_secret):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client secret")

    # Atomic revoke: prevents concurrent refresh race (TOCTOU)
    collection = OAuth2Token.get_motor_collection()
    matched = await collection.find_one_and_update(
        {"_id": token_record.id, "revoked": False},
        {"$set": {"revoked": True}},
    )
    if matched is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token already revoked")

    return await _issue_oauth2_tokens(
        client_id, token_record.user_id, token_record.scope
    )


async def revoke_token(token: str, client_id: str, client_secret: str | None = None) -> None:
    """Revoke an access or refresh token (RFC 7009 — always 200).

    Verifies caller is the owning client before revoking.
    """
    # Verify client exists and authenticate
    client = await OAuth2Client.find_one(OAuth2Client.client_id == client_id)
    if not client:
        return  # RFC 7009: always 200, even on invalid client

    if client.token_endpoint_auth_method != "none":
        if not client_secret or not client.client_secret:
            return
        if not verify_password(client_secret, client.client_secret):
            return

    # Try access token (only revoke if it belongs to this client)
    record = await OAuth2Token.find_one(
        OAuth2Token.access_token == token, OAuth2Token.client_id == client_id
    )
    if record:
        record.revoked = True
        await record.save()
        return

    # Try refresh token
    record = await OAuth2Token.find_one(
        OAuth2Token.refresh_token == token, OAuth2Token.client_id == client_id
    )
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
        expires_at=datetime.now(timezone.utc) + _OAUTH2_ACCESS_TOKEN_TTL,
    )
    await token.insert()

    result = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": int(_OAUTH2_ACCESS_TOKEN_TTL.total_seconds()),
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
    """Verify PKCE code_verifier — S256 only (plain method is rejected)."""
    if method != "S256":
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(computed, code_challenge)
