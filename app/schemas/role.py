from pydantic import BaseModel, Field


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    permissions: list[str] = []
    description: str | None = None


class RoleUpdateRequest(BaseModel):
    permissions: list[str] | None = None
    description: str | None = None


class RoleResponse(BaseModel):
    name: str
    permissions: list[str]
    description: str | None = None
