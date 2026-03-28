import pytest

from app.models.user import User
from app.services import auth_service


@pytest.mark.asyncio
async def test_verify_email_success(async_client, mock_smtp):
    """Verify email with valid token succeeds."""
    # Register user
    await async_client.post(
        "/auth/register",
        json={"email": "verify@test.com", "password": "Pass123!"},
    )
    user = await User.find_one(User.email == "verify@test.com")

    # Send verification
    await auth_service.send_verification(user)
    await user.sync()
    token = user.verification_token

    resp = await async_client.post(
        "/auth/verify-email", json={"token": token}
    )
    assert resp.status_code == 200

    # Verify user is now verified
    await user.sync()
    assert user.is_verified is True


@pytest.mark.asyncio
async def test_verify_email_invalid_token(async_client):
    """Verify with invalid token returns 400."""
    resp = await async_client.post(
        "/auth/verify-email", json={"token": "invalid-token-xyz"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_email_expired_token(async_client, mock_smtp):
    """Verify with expired token returns 400."""
    from datetime import datetime, timedelta, timezone

    await async_client.post(
        "/auth/register",
        json={"email": "expired@test.com", "password": "Pass123!"},
    )
    user = await User.find_one(User.email == "expired@test.com")
    await auth_service.send_verification(user)
    await user.sync()

    # Manually expire the token
    user.verification_token_expires = datetime.now(timezone.utc) - timedelta(hours=2)
    await user.save()

    resp = await async_client.post(
        "/auth/verify-email", json={"token": user.verification_token}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_double_verify_fails(async_client, mock_smtp):
    """Verifying an already-verified user returns 400."""
    await async_client.post(
        "/auth/register",
        json={"email": "double@test.com", "password": "Pass123!"},
    )
    user = await User.find_one(User.email == "double@test.com")
    await auth_service.send_verification(user)
    await user.sync()
    token = user.verification_token

    # First verify
    await async_client.post("/auth/verify-email", json={"token": token})

    # Second verify with same token should fail (token cleared)
    resp = await async_client.post("/auth/verify-email", json={"token": token})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_forgot_password_sends_email(async_client, mock_smtp):
    """Forgot password sends reset email for existing user."""
    await async_client.post(
        "/auth/register",
        json={"email": "reset@test.com", "password": "OldPass123!"},
    )
    resp = await async_client.post(
        "/auth/forgot-password", json={"email": "reset@test.com"}
    )
    assert resp.status_code == 200
    mock_smtp.assert_called()


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_still_200(async_client, mock_smtp):
    """Forgot password with unknown email returns 200 (no enumeration)."""
    resp = await async_client.post(
        "/auth/forgot-password", json={"email": "nobody@test.com"}
    )
    assert resp.status_code == 200
    mock_smtp.assert_not_called()


@pytest.mark.asyncio
async def test_reset_password_success(async_client, mock_smtp):
    """Reset password with valid token changes the password."""
    await async_client.post(
        "/auth/register",
        json={"email": "rp@test.com", "password": "OldPass123!"},
    )
    await async_client.post(
        "/auth/forgot-password", json={"email": "rp@test.com"}
    )
    user = await User.find_one(User.email == "rp@test.com")
    await user.sync()
    token = user.reset_token

    resp = await async_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPass456!"},
    )
    assert resp.status_code == 200

    # Login with new password
    resp = await async_client.post(
        "/auth/login",
        json={"email": "rp@test.com", "password": "NewPass456!"},
    )
    assert resp.status_code == 200

    # Old password no longer works
    resp = await async_client.post(
        "/auth/login",
        json={"email": "rp@test.com", "password": "OldPass123!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reset_password_expired_token(async_client, mock_smtp):
    """Reset with expired token returns 400."""
    from datetime import datetime, timedelta, timezone

    await async_client.post(
        "/auth/register",
        json={"email": "exp_reset@test.com", "password": "Pass123!"},
    )
    await async_client.post(
        "/auth/forgot-password", json={"email": "exp_reset@test.com"}
    )
    user = await User.find_one(User.email == "exp_reset@test.com")
    await user.sync()

    user.reset_token_expires = datetime.now(timezone.utc) - timedelta(hours=1)
    await user.save()

    resp = await async_client.post(
        "/auth/reset-password",
        json={"token": user.reset_token, "new_password": "NewPass123!"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_email_rate_limit(async_client, mock_smtp):
    """4th email request within 1 hour returns 429."""
    await async_client.post(
        "/auth/register",
        json={"email": "rate@test.com", "password": "Pass123!"},
    )
    # 3 requests should succeed
    for _ in range(3):
        resp = await async_client.post(
            "/auth/forgot-password", json={"email": "rate@test.com"}
        )
        assert resp.status_code == 200

    # 4th should be rate limited
    resp = await async_client.post(
        "/auth/forgot-password", json={"email": "rate@test.com"}
    )
    assert resp.status_code == 429
