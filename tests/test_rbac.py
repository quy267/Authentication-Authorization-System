import pytest


@pytest.mark.asyncio
async def test_admin_can_create_role(async_client, admin_token):
    """Admin can create a new role."""
    resp = await async_client.post(
        "/roles",
        json={"name": "moderator", "permissions": ["users:read"], "description": "Mod"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "moderator"


@pytest.mark.asyncio
async def test_admin_can_list_roles(async_client, admin_token):
    """Admin can list all roles."""
    resp = await async_client.get(
        "/roles", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "admin" in names
    assert "user" in names


@pytest.mark.asyncio
async def test_admin_can_update_role(async_client, admin_token):
    """Admin can update role permissions."""
    # Create role first
    await async_client.post(
        "/roles",
        json={"name": "editor", "permissions": []},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = await async_client.put(
        "/roles/editor",
        json={"permissions": ["users:read", "users:write"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "users:write" in resp.json()["permissions"]


@pytest.mark.asyncio
async def test_admin_can_delete_custom_role(async_client, admin_token):
    """Admin can delete non-default roles."""
    await async_client.post(
        "/roles",
        json={"name": "temp", "permissions": []},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = await async_client.delete(
        "/roles/temp", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_delete_default_roles(async_client, admin_token):
    """Cannot delete built-in admin or user roles."""
    resp = await async_client.delete(
        "/roles/admin", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 400

    resp = await async_client.delete(
        "/roles/user", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_admin_cannot_access_role_endpoints(async_client):
    """Regular user cannot access role CRUD."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "user@test.com", "password": "User123!"},
    )
    token = reg.json()["access_token"]

    resp = await async_client.get(
        "/roles", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_assign_roles(async_client, admin_token):
    """Admin can assign roles to users."""
    # Create a regular user
    reg = await async_client.post(
        "/auth/register",
        json={"email": "regular@test.com", "password": "Pass123!"},
    )
    # Get user ID from DB
    from app.models.user import User
    user = await User.find_one(User.email == "regular@test.com")

    resp = await async_client.put(
        f"/users/{user.id}/roles",
        json={"roles": ["admin", "user"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "admin" in resp.json()["roles"]


@pytest.mark.asyncio
async def test_admin_can_list_users(async_client, admin_token):
    """Admin can list all users."""
    resp = await async_client.get(
        "/users", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_require_permission_blocks_unauthorized(async_client, admin_token):
    """require_permission blocks users without the needed permission."""
    # Create a role with no permissions
    from app.main import seed_default_roles
    await seed_default_roles()

    # Regular user only has "user" role with "users:read" permission
    reg = await async_client.post(
        "/auth/register",
        json={"email": "limited@test.com", "password": "Pass123!"},
    )
    token = reg.json()["access_token"]

    # Try admin-only endpoint (requires "admin" role)
    resp = await async_client.get(
        "/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# role_service coverage: duplicate name (line 12), non-existent update (31),
# description-only update (35), delete non-existent (46), invalid names (55)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_duplicate_role_returns_409(async_client, admin_token):
    """Creating a role with an existing name returns 409."""
    await async_client.post(
        "/roles",
        json={"name": "dup_role", "permissions": ["users:read"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = await async_client.post(
        "/roles",
        json={"name": "dup_role", "permissions": ["users:read"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_nonexistent_role_returns_404(async_client, admin_token):
    """Updating a role that does not exist returns 404."""
    resp = await async_client.put(
        "/roles/nonexistent_role",
        json={"permissions": ["users:read"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_role_description_only(async_client, admin_token):
    """Updating only description (permissions=None) preserves permissions."""
    await async_client.post(
        "/roles",
        json={"name": "desc_role", "permissions": ["users:read"], "description": "Old"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = await async_client.put(
        "/roles/desc_role",
        json={"description": "New description"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "New description"
    assert "users:read" in data["permissions"]


@pytest.mark.asyncio
async def test_delete_nonexistent_role_returns_404(async_client, admin_token):
    """Deleting a role that does not exist returns 404."""
    resp = await async_client.delete(
        "/roles/ghost_role",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_assign_invalid_role_names_returns_400(async_client, admin_token):
    """Assigning non-existent role names to a user returns 400."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "validate_roles@test.com", "password": "Pass123!"},
    )
    from app.models.user import User
    user = await User.find_one(User.email == "validate_roles@test.com")

    resp = await async_client.put(
        f"/users/{user.id}/roles",
        json={"roles": ["nonexistent_role_xyz"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# user_service coverage: invalid ObjectId in update_user_roles (line 16/19),
# invalid ObjectId in revoke_user_sessions (32), non-existent user revoke (35)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_roles_invalid_object_id_returns_400(async_client, admin_token):
    """Updating roles with an invalid ObjectId returns 400."""
    resp = await async_client.put(
        "/users/not-a-valid-id/roles",
        json={"roles": ["user"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_roles_nonexistent_user_returns_404(async_client, admin_token):
    """Updating roles for a valid but non-existent user ID returns 404."""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await async_client.put(
        f"/users/{fake_id}/roles",
        json={"roles": ["user"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_sessions_invalid_object_id_returns_400(async_client, admin_token):
    """Revoking sessions with an invalid ObjectId returns 400."""
    resp = await async_client.post(
        "/users/not-a-valid-id/revoke-sessions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_revoke_sessions_nonexistent_user_returns_404(async_client, admin_token):
    """Revoking sessions for a valid but non-existent user ID returns 404."""
    from bson import ObjectId
    fake_id = str(ObjectId())
    resp = await async_client.post(
        f"/users/{fake_id}/revoke-sessions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_sessions_success(async_client, admin_token):
    """Admin can revoke all sessions for an existing user."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "revokable@test.com", "password": "Pass123!"},
    )
    from app.models.user import User
    user = await User.find_one(User.email == "revokable@test.com")

    resp = await async_client.post(
        f"/users/{user.id}/revoke-sessions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "revoked" in resp.json()["message"].lower()
