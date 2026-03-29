from fastapi import HTTPException, status

from app.models.role import Role

_DEFAULT_ROLES = {"admin", "user"}


async def create_role(name: str, permissions: list[str], description: str | None) -> Role:
    """Create a new role. Raises 409 if name already exists."""
    existing = await Role.find_one(Role.name == name)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Role already exists")
    role = Role(name=name, permissions=permissions, description=description)
    await role.insert()
    return role


async def list_roles() -> list[Role]:
    """Return all roles."""
    return await Role.find_all().to_list()


async def update_role(
    role_name: str,
    permissions: list[str] | None,
    description: str | None,
) -> Role:
    """Update an existing role. Raises 404 if not found."""
    role = await Role.find_one(Role.name == role_name)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if permissions is not None:
        role.permissions = permissions
    if description is not None:
        role.description = description
    await role.save()
    return role


async def delete_role(role_name: str) -> None:
    """Delete a role. Raises 400 for default roles, 404 if not found."""
    if role_name in _DEFAULT_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete default role")
    role = await Role.find_one(Role.name == role_name)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    await role.delete()


async def validate_role_names(names: list[str]) -> None:
    """Raise 400 if any name in the list doesn't correspond to an existing role."""
    existing = {r.name for r in await Role.find_all().to_list()}
    invalid = [n for n in names if n not in existing]
    if invalid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Roles not found: {invalid}",
        )
