import pytest

from app.models.user import User
from app.models.role import Role


@pytest.mark.asyncio
async def test_create_user(async_client):
    """User can be created and persisted."""
    user = User(
        email="test@example.com",
        hashed_password="fakehash",
    )
    await user.insert()

    found = await User.find_one(User.email == "test@example.com")
    assert found is not None
    assert found.email == "test@example.com"
    assert found.roles == ["user"]
    assert found.is_active is True
    assert found.is_verified is False


@pytest.mark.asyncio
async def test_user_email_uniqueness(async_client):
    """Duplicate emails are rejected."""
    await User(email="dup@example.com", hashed_password="h1").insert()
    with pytest.raises(Exception):
        await User(email="dup@example.com", hashed_password="h2").insert()


@pytest.mark.asyncio
async def test_user_default_timestamps(async_client):
    """User gets created_at and updated_at timestamps."""
    user = User(email="ts@example.com", hashed_password="h")
    await user.insert()
    assert user.created_at is not None
    assert user.updated_at is not None


@pytest.mark.asyncio
async def test_create_role(async_client):
    """Role can be created with permissions."""
    role = Role(
        name="admin",
        permissions=["users:read", "users:write", "roles:manage"],
        description="Full access",
    )
    await role.insert()

    found = await Role.find_one(Role.name == "admin")
    assert found is not None
    assert "users:write" in found.permissions


@pytest.mark.asyncio
async def test_role_name_uniqueness(async_client):
    """Duplicate role names are rejected."""
    await Role(name="editor", permissions=[]).insert()
    with pytest.raises(Exception):
        await Role(name="editor", permissions=[]).insert()
