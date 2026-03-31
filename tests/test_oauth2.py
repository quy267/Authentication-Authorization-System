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

    # Refresh (confidential client requires client_secret)
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": old_refresh,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
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

    # Revoke (now requires client authentication)
    resp = await async_client.post(
        "/oauth/revoke", json={
            "token": access_tok,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        }
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


# --- Coverage gap tests: authorize() error paths ---


@pytest.mark.asyncio
async def test_authorize_invalid_redirect_uri(async_client, admin_token):
    """Authorize with redirect_uri not in client list returns 400 (line 60)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "redir@test.com")

    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://evil.com/callback",
            "scope": "users:read",
            "state": "s",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_authorize_grant_type_not_allowed(async_client, admin_token):
    """Client without authorization_code grant type gets 400 (line 63)."""
    # Create a client that only supports client_credentials
    resp = await async_client.post(
        "/oauth/clients",
        json={
            "client_name": "CC Only",
            "redirect_uris": ["https://example.com/callback"],
            "allowed_scopes": ["users:read"],
            "grant_types": ["client_credentials"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    client = resp.json()
    user_token = await _get_user_token(async_client, "nogrant@test.com")

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
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_authorize_unsupported_pkce_method(async_client, admin_token):
    """PKCE with method other than S256 returns 400 (line 74)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "plainpkce@test.com")

    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://example.com/callback",
            "scope": "users:read",
            "state": "s",
            "code_challenge": "some_challenge",
            "code_challenge_method": "plain",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 400


# --- Coverage gap tests: exchange_code() error paths ---


@pytest.mark.asyncio
async def test_exchange_code_invalid_code(async_client):
    """Exchange with nonexistent code returns 400 (line 111)."""
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": "nonexistent_code",
            "redirect_uri": "https://example.com/callback",
            "client_id": "any_client",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_exchange_code_client_mismatch(async_client, admin_token):
    """Exchange with wrong client_id returns 400 (line 125)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "climis@test.com")

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
            "client_id": "wrong_client_id",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_exchange_code_redirect_uri_mismatch(async_client, admin_token):
    """Exchange with wrong redirect_uri returns 400 (line 128)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "redirmis@test.com")

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
            "redirect_uri": "https://wrong.com/callback",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_exchange_code_invalid_client_secret(async_client, admin_token):
    """Exchange with wrong client_secret returns 400 (line 140)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "badsec@test.com")

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
            "client_secret": "wrong_secret",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_exchange_code_missing_client_secret(async_client, admin_token):
    """Confidential client exchange without secret returns 400 (line 138)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "nosec@test.com")

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
            # No client_secret
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_exchange_code_pkce_verifier_missing(async_client, admin_token):
    """PKCE code exchange without code_verifier returns 400 (line 145)."""
    client = await _create_public_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "noverif@test.com")
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
            # No code_verifier
        },
    )
    assert resp.status_code == 400


# --- Coverage gap tests: client_credentials_grant() error paths ---


@pytest.mark.asyncio
async def test_client_credentials_grant_type_not_allowed(async_client, admin_token):
    """Client without client_credentials grant type gets 400 (line 158/173)."""
    # Public client only has authorization_code grant
    client = await _create_public_client(async_client, admin_token)

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client["client_id"],
            "client_secret": "anything",
            "scope": "users:read",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_client_credentials_invalid_secret(async_client, admin_token):
    """Client credentials with wrong secret returns 400 (line 181)."""
    client = await _create_confidential_client(async_client, admin_token)

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client["client_id"],
            "client_secret": "wrong_secret",
            "scope": "users:read",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_client_credentials_invalid_scope(async_client, admin_token):
    """Client credentials with disallowed scope returns 400 (line 186)."""
    client = await _create_confidential_client(async_client, admin_token)

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "scope": "admin:everything",
        },
    )
    assert resp.status_code == 400


# --- Coverage gap tests: refresh_oauth2_token() error paths ---


@pytest.mark.asyncio
async def test_refresh_token_client_mismatch(async_client, admin_token):
    """Refresh with wrong client_id returns 400 (line 204)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "refmis@test.com")

    # Get tokens via auth code
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
    refresh_tok = resp.json()["refresh_token"]

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "client_id": "wrong_client_id",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_refresh_token_invalid_secret(async_client, admin_token):
    """Refresh with wrong client_secret returns 400 (line 213-215)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "refsec@test.com")

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
    refresh_tok = resp.json()["refresh_token"]

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "client_id": client["client_id"],
            "client_secret": "wrong_secret",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_refresh_token_missing_secret_confidential(async_client, admin_token):
    """Confidential client refresh without secret returns 400 (line 213)."""
    client = await _create_confidential_client(async_client, admin_token)
    user_token = await _get_user_token(async_client, "refnosec@test.com")

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
    refresh_tok = resp.json()["refresh_token"]

    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "client_id": client["client_id"],
            # No client_secret
        },
    )
    assert resp.status_code == 400


# --- Coverage gap tests: revoke_token() error paths ---


@pytest.mark.asyncio
async def test_revoke_invalid_client(async_client):
    """Revoke with nonexistent client_id returns 200 per RFC 7009 (line 239)."""
    resp = await async_client.post(
        "/oauth/revoke",
        json={
            "token": "some_token",
            "client_id": "nonexistent",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revoke_wrong_client_secret(async_client, admin_token):
    """Revoke with wrong secret silently returns 200 (line 243-245)."""
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

    resp = await async_client.post(
        "/oauth/revoke",
        json={
            "token": access_tok,
            "client_id": client["client_id"],
            "client_secret": "wrong_secret",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revoke_missing_secret_confidential(async_client, admin_token):
    """Revoke without secret for confidential client returns 200 (line 243)."""
    client = await _create_confidential_client(async_client, admin_token)

    resp = await async_client.post(
        "/oauth/revoke",
        json={
            "token": "some_token",
            "client_id": client["client_id"],
            # No client_secret
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revoke_token_not_owned_by_client(async_client, admin_token):
    """Revoke token belonging to different client returns 200 (lines 257-262)."""
    client1 = await _create_confidential_client(async_client, admin_token)
    # Create a second client
    resp = await async_client.post(
        "/oauth/clients",
        json={
            "client_name": "Other App",
            "redirect_uris": ["https://other.com/callback"],
            "allowed_scopes": ["users:read"],
            "grant_types": ["authorization_code", "client_credentials", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    client2 = resp.json()

    # Get token from client1
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client1["client_id"],
            "client_secret": client1["client_secret"],
            "scope": "users:read",
        },
    )
    access_tok = resp.json()["access_token"]

    # Try to revoke client1's token using client2 credentials
    resp = await async_client.post(
        "/oauth/revoke",
        json={
            "token": access_tok,
            "client_id": client2["client_id"],
            "client_secret": client2["client_secret"],
        },
    )
    assert resp.status_code == 200
