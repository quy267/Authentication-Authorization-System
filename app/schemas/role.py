from pydantic import BaseModel


class RoleCreateRequest(BaseModel):
    name: str
    permissions: list[str] = []
    description: str | None = None


class RoleUpdateRequest(BaseModel):
    permissions: list[str] | None = None
    description: str | None = None


class RoleResponse(BaseModel):
    name: str
    permissions: list[str]
    description: str | None = None
