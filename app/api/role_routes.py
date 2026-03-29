from fastapi import APIRouter, Depends, status

from app.api.deps import require_role
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.role import RoleCreateRequest, RoleResponse, RoleUpdateRequest
from app.services import role_service

router = APIRouter(prefix="/roles", tags=["roles"])


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreateRequest,
    current_user: User = Depends(require_role("admin")),
):
    return await role_service.create_role(body.name, body.permissions, body.description)


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    current_user: User = Depends(require_role("admin")),
):
    return await role_service.list_roles()


@router.put("/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    body: RoleUpdateRequest,
    current_user: User = Depends(require_role("admin")),
):
    return await role_service.update_role(role_name, body.permissions, body.description)


@router.delete("/{role_name}", response_model=MessageResponse)
async def delete_role(
    role_name: str,
    current_user: User = Depends(require_role("admin")),
):
    await role_service.delete_role(role_name)
    return {"message": f"Role '{role_name}' deleted"}
