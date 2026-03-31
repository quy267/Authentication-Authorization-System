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


# ---------------------------------------------------------------------------
# Coverage gap: deps.py line 29 — refresh token used on protected endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refresh_token_rejected_on_protected_endpoint(async_client):
    """Using a refresh token (type!=access) on a protected endpoint returns 401."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "reftok@example.com", "password": "Secret123!"},
    )
    refresh_tok = reg.json()["refresh_token"]

    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "x"},
        headers={"Authorization": f"Bearer {refresh_tok}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token type"


# ---------------------------------------------------------------------------
# Coverage gap: deps.py line 42 — valid JWT but user deleted from DB
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deleted_user_token_rejected(async_client):
    """Token for a user that has been deleted from the DB returns 401."""
    from app.models.user import User

    reg = await async_client.post(
        "/auth/register",
        json={"email": "ghost@example.com", "password": "Secret123!"},
    )
    token = reg.json()["access_token"]

    # Delete the user directly from DB
    user = await User.find_one(User.email == "ghost@example.com")
    await user.delete()

    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "User not found"


# ---------------------------------------------------------------------------
# Coverage gap: deps.py line 48 — disabled user (is_active=False)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disabled_user_token_rejected(async_client):
    """Token for a disabled user returns 403 'Account disabled'."""
    from app.models.user import User

    reg = await async_client.post(
        "/auth/register",
        json={"email": "disabled@example.com", "password": "Secret123!"},
    )
    token = reg.json()["access_token"]

    user = await User.find_one(User.email == "disabled@example.com")
    user.is_active = False
    await user.save()

    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account disabled"


# ---------------------------------------------------------------------------
# Coverage gap: deps.py line 57 — token issued before session revocation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revoked_session_token_rejected(async_client):
    """Token issued before session revocation returns 401."""
    import time
    from app.core.database import get_redis
    from app.core.security import decode_token

    reg = await async_client.post(
        "/auth/register",
        json={"email": "revoked@example.com", "password": "Secret123!"},
    )
    token = reg.json()["access_token"]

    # Extract user_id from the token
    payload = decode_token(token)
    user_id = payload["sub"]

    # Revoke all sessions — set revoked_at to future of token iat
    redis = get_redis()
    await redis.setex(f"revoked_at:{user_id}", 600, str(int(time.time()) + 10))

    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Session has been revoked"


# ---------------------------------------------------------------------------
# Coverage gap: deps.py lines 79-90 — require_permission dependency
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_require_permission_grants_and_denies(async_client):
    """require_permission allows users with the permission and denies without."""
    from app.api.deps import require_permission
    from app.models.user import User
    from app.models.role import Role
    from app.main import seed_default_roles
    from fastapi import HTTPException

    # Seed default roles (admin + user) into DB
    await seed_default_roles()

    # Register and promote an admin user
    await async_client.post(
        "/auth/register",
        json={"email": "permadmin@example.com", "password": "Secret123!"},
    )
    admin_user = await User.find_one(User.email == "permadmin@example.com")
    admin_user.roles = ["admin", "user"]
    await admin_user.save()

    # Test: admin has 'roles:manage' permission → should pass
    check_fn = require_permission("roles:manage")
    result = await check_fn(user=admin_user)
    assert result.email == "permadmin@example.com"

    # Register a plain user (role 'user' only — no 'roles:manage')
    await async_client.post(
        "/auth/register",
        json={"email": "permplain@example.com", "password": "Secret123!"},
    )
    plain_user = await User.find_one(User.email == "permplain@example.com")

    # Test: plain user does NOT have 'roles:manage' → should raise 403
    check_fn_deny = require_permission("roles:manage")
    try:
        await check_fn_deny(user=plain_user)
        assert False, "Should have raised HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "roles:manage" in exc.detail


# ---------------------------------------------------------------------------
# Coverage gap: auth_service.py lines 94-96 — login with disabled account
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_disabled_account(async_client):
    """Login with a disabled account returns 401 'Invalid credentials'."""
    from app.models.user import User

    await async_client.post(
        "/auth/register",
        json={"email": "inact@example.com", "password": "Secret123!"},
    )
    user = await User.find_one(User.email == "inact@example.com")
    user.is_active = False
    await user.save()

    resp = await async_client.post(
        "/auth/login",
        json={"email": "inact@example.com", "password": "Secret123!"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


# ---------------------------------------------------------------------------
# Coverage gap: auth_service.py lines 131-132, 141-142 — logout with bad tokens
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_logout_with_bad_refresh_token(async_client):
    """Logout succeeds even when refresh token is garbage (access still blacklisted)."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "badref@example.com", "password": "Secret123!"},
    )
    tokens = reg.json()

    resp = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "not-a-valid-jwt"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    # Logout should still succeed (access token is blacklisted, bad refresh is ignored)
    assert resp.status_code == 200

    # Verify access token is now blacklisted
    resp2 = await async_client.post(
        "/auth/logout",
        json={"refresh_token": "x"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp2.status_code == 401


# ---------------------------------------------------------------------------
# Coverage gap: auth_service.py line 219-220 — verify already-verified email
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verify_already_verified_email(async_client, mock_smtp):
    """Verifying an already-verified email returns 400."""
    from app.models.user import User
    from datetime import datetime, timedelta, timezone

    await async_client.post(
        "/auth/register",
        json={"email": "vfy@example.com", "password": "Secret123!"},
    )
    user = await User.find_one(User.email == "vfy@example.com")

    # Manually set verification token and mark as verified
    user.verification_token = "test-verify-token"
    user.verification_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    user.is_verified = True
    await user.save()

    resp = await async_client.post(
        "/auth/verify-email",
        json={"token": "test-verify-token"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Already verified"
