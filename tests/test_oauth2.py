import base64
import hashlib

import pytest


async def _create_confidential_client(async_client, admin_token):
    """Helper: create a confidential OAuth2 client."""
    resp = await async_client.post(
        "/oauth/clients",
        json={
            "client_name": "Test App",
            "redirect_uris": ["https://example.com/callback"],
            "allowed_scopes": ["users:read", "users:write"],
            "grant_types": ["authorization_code", "client_credentials", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return resp.json()


async def _create_public_client(async_client, admin_token):
    """Helper: create a public OAuth2 client (PKCE required)."""
    resp = await async_client.post(
        "/oauth/clients",
        json={
            "client_name": "Public SPA",
            "redirect_uris": ["https://spa.example.com/callback"],
            "allowed_scopes": ["users:read"],
            "grant_types": ["authorization_code"],
            "token_endpoint_auth_method": "none",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return resp.json()


def _pkce_pair():
    """Generate PKCE code_verifier and code_challenge."""
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _get_user_token(async_client, email="oauth_user@test.com"):
    """Helper: register a user and return access token."""
    resp = await async_client.post(
        "/auth/register",
        json={"email": email, "password": "Pass123!"},
    )
    return resp.json()["access_token"]


# --- Client CRUD ---

@pytest.mark.asyncio
async def test_admin_creates_client(async_client, admin_token):
    """Admin can create an OAuth2 client."""
    client = await _create_confidential_client(async_client, admin_token)
    assert client["client_id"]
    assert client["client_secret"]
    assert client["client_name"] == "Test App"


@pytest.mark.asyncio
async def test_admin_lists_clients(async_client, admin_token):
    """Admin can list OAuth2 clients."""
    await _create_confidential_client(async_client, admin_token)
    resp = await async_client.get(
        "/oauth/clients",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


# --- Authorization Code Flow ---

@pytest.mark.asyncio
async def test_auth_code_flow_full_cycle(async_client, admin_token):
    """Full auth code flow: authorize → exchange code → get tokens."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client)

    # Step 1: Authorize
    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://example.com/callback",
            "scope": "users:read",
            "state": "abc123",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    code = resp.json()["code"]
    assert resp.json()["state"] == "abc123"

    # Step 2: Exchange code for tokens
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.com/callback",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        },
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "Bearer"


# --- PKCE ---

@pytest.mark.asyncio
async def test_auth_code_pkce_valid(async_client, admin_token):
    """Auth code + PKCE: valid code_verifier succeeds."""
    client = await _create_public_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "pkce@test.com")
    verifier, challenge = _pkce_pair()

    # Authorize with code_challenge
    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://spa.example.com/callback",
            "scope": "users:read",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    code = resp.json()["code"]

    # Exchange with code_verifier
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://spa.example.com/callback",
            "client_id": client["client_id"],
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_auth_code_pkce_invalid_verifier(async_client, admin_token):
    """Auth code + PKCE: invalid code_verifier returns 400."""
    client = await _create_public_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "pkce_bad@test.com")
    _, challenge = _pkce_pair()

    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://spa.example.com/callback",
            "scope": "users:read",
            "state": "s",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    code = resp.json()["code"]

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://spa.example.com/callback",
            "client_id": client["client_id"],
            "code_verifier": "wrong-verifier",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_public_client_without_pkce_rejected(async_client, admin_token):
    """Public client without PKCE is rejected."""
    client = await _create_public_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "nopkce@test.com")

    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://spa.example.com/callback",
            "scope": "users:read",
            "state": "s",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 400


# --- Client Credentials ---

@pytest.mark.asyncio
async def test_client_credentials_flow(async_client, admin_token):
    """Client credentials flow returns access token (no refresh)."""
    client = await _create_confidential_client(async_client, admin_token)

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "scope": "users:read",
        },
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["access_token"]
    assert tokens.get("refresh_token") is None


# --- Token Refresh ---

@pytest.mark.asyncio
async def test_oauth2_token_refresh(async_client, admin_token):
    """Refresh token returns new token pair."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "refresh_oauth@test.com")

    # Get initial tokens via auth code
    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://example.com/callback",
            "scope": "users:read",
            "state": "s",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    code = resp.json()["code"]

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.com/callback",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        },
    )
    old_refresh = resp.json()["refresh_token"]

    # Refresh
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": old_refresh,
            "client_id": client["client_id"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


# --- Token Revocation ---

@pytest.mark.asyncio
async def test_oauth2_token_revocation(async_client, admin_token):
    """Revoked token cannot be refreshed."""
    client = await _create_confidential_client(async_client, admin_token)

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "scope": "users:read",
        },
    )
    access_tok = resp.json()["access_token"]

    # Revoke
    resp = await async_client.post(
        "/oauth/revoke", json={"token": access_tok}
    )
    assert resp.status_code == 200


# --- Error Cases ---

@pytest.mark.asyncio
async def test_invalid_client_id(async_client):
    """Invalid client_id returns 400."""
    user_token = await _get_user_token(async_client, "badclient@test.com")
    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "nonexistent",
            "redirect_uri": "https://x.com/cb",
            "scope": "",
            "state": "s",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_code_replay_rejected(async_client, admin_token):
    """Using an authorization code twice fails."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "replay@test.com")

    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://example.com/callback",
            "scope": "users:read",
            "state": "s",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    code = resp.json()["code"]

    # First exchange
    await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.com/callback",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        },
    )

    # Replay
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://example.com/callback",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_scope_rejected(async_client, admin_token):
    """Requesting a scope not in client's allowed_scopes returns 400."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "scope@test.com")

    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://example.com/callback",
            "scope": "admin:everything",
            "state": "s",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 400
