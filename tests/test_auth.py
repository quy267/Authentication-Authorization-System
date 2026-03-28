import pytest


@pytest.mark.asyncio
async def test_register_success(async_client):
    """Register with valid data returns 201 + tokens."""
    resp = await async_client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "Secret123!"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(async_client):
    """Register with existing email returns 409."""
    await async_client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "Pass123!"},
    )
    resp = await async_client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "Pass456!"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(async_client):
    """Login with valid credentials returns tokens."""
    await async_client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "Secret123!"},
    )
    resp = await async_client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "Secret123!"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(async_client):
    """Login with wrong password returns 401."""
    await async_client.post(
        "/auth/register",
        json={"email": "wrong@example.com", "password": "Correct123!"},
    )
    resp = await async_client.post(
        "/auth/login",
        json={"email": "wrong@example.com", "password": "WrongPass!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(async_client):
    """Login with unknown email returns 401."""
    resp = await async_client.post(
        "/auth/login",
        json={"email": "noone@example.com", "password": "Whatever!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token(async_client):
    """Access protected endpoint with valid token succeeds."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "prot@example.com", "password": "Secret123!"},
    )
    token = reg.json()["access_token"]
    resp = await async_client.get(
        "/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(async_client):
    """Access auth-required endpoint without token returns 403."""
    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "fake"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token(async_client):
    """Access with garbage token returns 401."""
    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "fake"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_blacklists_tokens(async_client):
    """After logout, access token is blacklisted."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "out@example.com", "password": "Secret123!"},
    )
    tokens = reg.json()

    # Logout
    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200

    # Try using the blacklisted access token on a protected endpoint
    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "x"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(async_client):
    """Refresh returns a new token pair."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "ref@example.com", "password": "Secret123!"},
    )
    old_tokens = reg.json()

    resp = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": old_tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"] != old_tokens["access_token"]
    assert new_tokens["refresh_token"] != old_tokens["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_blacklisted_token_rejected(async_client):
    """Using a refresh token twice fails (old one is blacklisted)."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "ref2@example.com", "password": "Secret123!"},
    )
    refresh_tok = reg.json()["refresh_token"]

    # First refresh succeeds
    resp1 = await async_client.post(
        "/auth/refresh", json={"refresh_token": refresh_tok}
    )
    assert resp1.status_code == 200

    # Second refresh with same token fails
    resp2 = await async_client.post(
        "/auth/refresh", json={"refresh_token": refresh_tok}
    )
    assert resp2.status_code == 401
