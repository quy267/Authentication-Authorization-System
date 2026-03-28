import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_account_lockout_after_failed_attempts(async_client):
    """5 failed logins lock the account (423)."""
    await async_client.post(
        "/auth/register",
        json={"email": "lock@test.com", "password": "Correct123!"},
    )

    # Fail N times (LOCKOUT_THRESHOLD = 5)
    for _ in range(settings.LOCKOUT_THRESHOLD):
        resp = await async_client.post(
            "/auth/login",
            json={"email": "lock@test.com", "password": "Wrong!"},
        )
        assert resp.status_code == 401

    # Next attempt should be locked
    resp = await async_client.post(
        "/auth/login",
        json={"email": "lock@test.com", "password": "Correct123!"},
    )
    assert resp.status_code == 423


@pytest.mark.asyncio
async def test_lockout_persists_during_window(async_client):
    """6th attempt during lockout is still 423."""
    await async_client.post(
        "/auth/register",
        json={"email": "lock2@test.com", "password": "Correct123!"},
    )

    for _ in range(settings.LOCKOUT_THRESHOLD):
        await async_client.post(
            "/auth/login",
            json={"email": "lock2@test.com", "password": "Wrong!"},
        )

    # Both wrong and correct passwords are blocked
    resp = await async_client.post(
        "/auth/login",
        json={"email": "lock2@test.com", "password": "Wrong!"},
    )
    assert resp.status_code == 423


@pytest.mark.asyncio
async def test_successful_login_resets_counter(async_client):
    """Successful login resets the failed attempt counter."""
    await async_client.post(
        "/auth/register",
        json={"email": "reset_counter@test.com", "password": "Pass123!"},
    )

    # Fail a few times (but not enough to lock)
    for _ in range(settings.LOCKOUT_THRESHOLD - 1):
        await async_client.post(
            "/auth/login",
            json={"email": "reset_counter@test.com", "password": "Wrong!"},
        )

    # Successful login
    resp = await async_client.post(
        "/auth/login",
        json={"email": "reset_counter@test.com", "password": "Pass123!"},
    )
    assert resp.status_code == 200

    # Fail again — counter should be reset, so this shouldn't lock
    for _ in range(settings.LOCKOUT_THRESHOLD - 1):
        await async_client.post(
            "/auth/login",
            json={"email": "reset_counter@test.com", "password": "Wrong!"},
        )

    # Should still be able to login (not locked)
    resp = await async_client.post(
        "/auth/login",
        json={"email": "reset_counter@test.com", "password": "Pass123!"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_revoke_sessions(async_client, admin_token):
    """Admin can revoke all sessions for a user."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "revoke@test.com", "password": "Pass123!"},
    )
    from app.models.user import User
    user = await User.find_one(User.email == "revoke@test.com")

    resp = await async_client.post(
        f"/users/{user.id}/revoke-sessions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "revoked" in resp.json()["message"]
