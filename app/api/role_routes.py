from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.role import RoleCreateRequest, RoleResponse, RoleUpdateRequest

router = APIRouter(prefix="/roles", tags=["roles"])

DEFAULT_ROLES = {"admin", "user"}


@router.post(
    "", response_model=RoleResponse, status_code=status.HTTP_201_CREATED
)
async def create_role(
    body: RoleCreateRequest,
    current_user: User = Depends(require_role("admin")),
):
    existing = await Role.find_one(Role.name == body.name)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Role already exists")
    role = Role(name=body.name, permissions=body.permissions, description=body.description)
    await role.insert()
    return role


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    current_user: User = Depends(require_role("admin")),
):
    return await Role.find_all().to_list()


@router.put("/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    body: RoleUpdateRequest,
    current_user: User = Depends(require_role("admin")),
):
    role = await Role.find_one(Role.name == role_name)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if body.permissions is not None:
        role.permissions = body.permissions
    if body.description is not None:
        role.description = body.description
    await role.save()
    return role


@router.delete("/{role_name}", response_model=MessageResponse)
async def delete_role(
    role_name: str,
    current_user: User = Depends(require_role("admin")),
):
    if role_name in DEFAULT_ROLES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cannot delete default role"
        )
    role = await Role.find_one(Role.name == role_name)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    await role.delete()
    return {"message": f"Role '{role_name}' deleted"}
