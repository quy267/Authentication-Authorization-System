"""End-to-end integration journey tests."""
import base64
import hashlib

import pytest

from app.models.user import User


@pytest.mark.asyncio
async def test_full_user_journey(async_client, mock_smtp):
    """Register → verify email → login → access protected → logout."""
    from app.services import auth_service

    # 1. Register
    resp = await async_client.post(
        "/auth/register",
        json={"email": "journey@test.com", "password": "Journey123!"},
    )
    assert resp.status_code == 201
    tokens = resp.json()

    # 2. Send + verify email
    user = await User.find_one(User.email == "journey@test.com")
    await auth_service.send_verification(user)
    await user.sync()
    resp = await async_client.post(
        "/auth/verify-email", json={"token": user.verification_token}
    )
    assert resp.status_code == 200

    # 3. Login
    resp = await async_client.post(
        "/auth/login",
        json={"email": "journey@test.com", "password": "Journey123!"},
    )
    assert resp.status_code == 200
    tokens = resp.json()

    # 4. Access protected endpoint
    resp = await async_client.get(
        "/health",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200

    # 5. Logout
    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200

    # 6. Old token rejected
    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "x"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_full_oauth2_journey(async_client, admin_token):
    """Create client → authorize → exchange code → use token → revoke."""
    # 1. Create OAuth2 client
    resp = await async_client.post(
        "/oauth/clients",
        json={
            "client_name": "Integration App",
            "redirect_uris": ["https://app.example.com/cb"],
            "allowed_scopes": ["users:read"],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    client = resp.json()

    # 2. Create user and authorize
    user_token = (await async_client.post(
        "/auth/register",
        json={"email": "oauth_journey@test.com", "password": "Pass123!"},
    )).json()["access_token"]

    resp = await async_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://app.example.com/cb",
            "scope": "users:read",
            "state": "mystate",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    code = resp.json()["code"]

    # 3. Exchange code
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://app.example.com/cb",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        },
    )
    assert resp.status_code == 200
    oauth_tokens = resp.json()

    # 4. Refresh
    resp = await async_client.post(
        "/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": oauth_tokens["refresh_token"],
            "client_id": client["client_id"],
        },
    )
    assert resp.status_code == 200

    # 5. Revoke
    resp = await async_client.post(
        "/oauth/revoke",
        json={"token": resp.json()["access_token"]},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_journey(async_client, admin_token):
    """Admin: login → create role → assign role → verify access."""
    from app.main import seed_default_roles
    await seed_default_roles()

    # 1. Create custom role
    resp = await async_client.post(
        "/roles",
        json={
            "name": "reviewer",
            "permissions": ["users:read", "users:write"],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201

    # 2. Create user and assign role
    await async_client.post(
        "/auth/register",
        json={"email": "reviewer@test.com", "password": "Reviewer123!"},
    )
    user = await User.find_one(User.email == "reviewer@test.com")
    resp = await async_client.put(
        f"/users/{user.id}/roles",
        json={"roles": ["reviewer", "user"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "reviewer" in resp.json()["roles"]

    # 3. List users
    resp = await async_client.get(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "reviewer@test.com" in emails
